from collections.abc import Sequence
from typing import cast

from sqlalchemy import CursorResult, Float, Row, delete, desc, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.models.gold_layer import DomainSynonymsModel, GoldDescriptionModel, GoldDescriptionTagModel, GoldTagModel


class TagManager:
    """Serviço responsável por auditar, limpar e unificar tags na Camada Ouro."""

    def __init__(self, db: Session):
        self.db = db

    def purge_stopwords(self, stopwords: list[str]) -> int:
        """
        Varre o banco e apaga graciosamente qualquer tag que bata exatamente com a lista de stopwords.
        Retorna o número de tags apagadas.
        """

        stopwords_clean = [w.strip().lower() for w in stopwords]

        junk_taks = self.db.scalars(
            select(GoldTagModel).where(func.lower(GoldTagModel.name).in_(stopwords_clean))
        ).all()

        if not junk_taks:
            return 0

        qtd_deleted = len(junk_taks)

        # Apaga via ORM para garantir que as associações com os documentos sejam removidas (Cascade)
        for tag in junk_taks:
            self.db.delete(tag)

        self.db.commit()
        return qtd_deleted

    def get_tag_relevance_count(self, limit: int = 30) -> Sequence[Row[tuple[str, int]]]:
        """
        Conta quantas vezes cada tag aparece associada a um documento.
        """
        stmt = (
            select(GoldTagModel.name, func.count(GoldDescriptionTagModel.description_id).label("total_usos"))
            .join(GoldDescriptionTagModel, GoldTagModel.tag_id == GoldDescriptionTagModel.tag_id)
            .group_by(GoldTagModel.tag_id, GoldTagModel.name)
            .order_by(text("total_usos DESC"))
            .limit(limit)
        )

        return self.db.execute(stmt).fetchall()

    def get_tag_relevance_tfidf(self, limit: int = 30):
        """
        Calcula a relevância global das tags usando a fórmula TF-IDF diretamente no PostgreSQL.
        Penaliza tags genéricas que aparecem em todo o acervo e destaca termos específicos importantes.
        """
        # 1. Pega o número total de documentos no acervo (N)
        total_docs = self.db.scalar(select(func.count(GoldDescriptionModel.description_id)))

        if not total_docs or total_docs == 0:
            return []

        # 2. Define os blocos matemáticos da Query
        df = func.count(GoldDescriptionTagModel.description_id)  # Quantas vezes a tag foi usada

        # IDF = ln( Total de Documentos / Uso da Tag )
        # Usamos cast para Float para evitar divisão inteira no PostgreSQL
        idf = func.ln(total_docs / func.cast(df, Float))

        # Score Global = DF * IDF
        tfidf_score = df * idf

        # 3. Executa a query agrupando e ordenando pelo maior score
        stmt = (
            select(GoldTagModel.name, df.label("frequencia"), idf.label("peso_idf"), tfidf_score.label("score_tfidf"))
            .join(GoldDescriptionTagModel, GoldTagModel.tag_id == GoldDescriptionTagModel.tag_id)
            .group_by(GoldTagModel.tag_id, GoldTagModel.name)
            .order_by(desc("score_tfidf"))
            .limit(limit)
        )

        # Retorna uma lista de tuplas estruturadas
        return self.db.execute(stmt).fetchall()

    def find_similar_tags(self, target_tag: str, threshold: float = 0.5) -> Sequence[Row[tuple[int, str, float]]]:
        """
        Busca tags com erros de digitação ou similaridade alta usando a extensão
        pg_trgm nativa do PostgreSQL.
        Retorna uma lista de tuplas com o id ,nome e o score de similaridade da tag.
        """
        target_lower = target_tag.lower()

        # Cria a expressão de similaridade do PostgreSQL
        similaridade = func.similarity(GoldTagModel.name, target_lower)

        stmt = (
            select(GoldTagModel.tag_id, GoldTagModel.name, similaridade.label("sim_score"))
            # Filtra apenas os que passam do limite de similaridade
            .where(similaridade >= threshold)
            # Ignora a própria palavra alvo
            .where(func.lower(GoldTagModel.name) != target_lower)
            # Ordena dos mais parecidos para os menos parecidos
            .order_by(desc("sim_score"))
            .limit(15)
        )

        return self.db.execute(stmt).fetchall()

    def merge_tags(self, canonical_id: int, ids_to_merge: list[int]) -> tuple[int, int]:
        """
        Fundir múltiplas tags erradas numa tag canônica.
        1. Salva os nomes das tags descartadas como sinônimos da canônica.
        2. Transfere todos os vínculos de documentos para a tag canônica.
        3. Apaga as tags mescladas da base.

        Retorna uma tupla: (Qtd de Documentos Atualizados, Qtd de Tags Apagadas)
        """
        if not ids_to_merge:
            return 0, 0

        # 1. Busca os nomes das tags que vão ser mescladas (futuros sinônimos)
        tags_mortas = self.db.scalars(select(GoldTagModel).where(GoldTagModel.tag_id.in_(ids_to_merge))).all()

        nomes_sinonimos = [t.name for t in tags_mortas]

        # 2. Transfere os Documentos de forma segura (Prevenção de Unique Constraint)
        # Busca todos os IDs de documentos que usavam as tags erradas
        docs_afetados = (
            self.db.execute(
                select(GoldDescriptionTagModel.description_id).where(GoldDescriptionTagModel.tag_id.in_(ids_to_merge))
            )
            .scalars()
            .all()
        )

        if docs_afetados:
            # Usamos set() para remover duplicidades se um mesmo documento tinha 2 tags erradas
            novos_vinculos = [{"description_id": doc_id, "tag_id": canonical_id} for doc_id in set(docs_afetados)]

            # Tenta inserir a tag canônica nesses documentos. Se o doc já tiver a tag, ignora silenciosamente.
            stmt_transfer = insert(GoldDescriptionTagModel).values(novos_vinculos).on_conflict_do_nothing()
            self.db.execute(stmt_transfer)

        # 3. Salva os Sinônimos na nova estrutura polimórfica
        if nomes_sinonimos:
            sinonimos_data = [
                {
                    "synonym_name": nome,
                    "category": "TAG",  # Define o discriminador do arco exclusivo
                    "canonical_tag_id": canonical_id,  # Alvo da FK de Tags
                    "canonical_entity_id": None,  # Garante a integridade exigida pelo CheckConstraint
                }
                for nome in nomes_sinonimos
            ]
            stmt_syn = (
                insert(DomainSynonymsModel)
                .values(sinonimos_data)
                .on_conflict_do_nothing()  # Baseado na restrição única composta (synonym_name, category)
            )
            self.db.execute(stmt_syn)

        # 4. Limpeza Final
        # Apaga os vínculos associativos antigos (caso o banco não esteja com CASCADE configurado)
        self.db.execute(delete(GoldDescriptionTagModel).where(GoldDescriptionTagModel.tag_id.in_(ids_to_merge)))

        # Apaga as tags da tabela principal
        resultado_delete = self.db.execute(delete(GoldTagModel).where(GoldTagModel.tag_id.in_(ids_to_merge)))

        resultado_delete = cast(CursorResult, resultado_delete)
        return len(docs_afetados), resultado_delete.rowcount
