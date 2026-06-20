import re
from collections.abc import Sequence
from typing import Any, Literal, cast

from sqlalchemy import CursorResult, Float, Row, delete, desc, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.logger import logger
from domains.archive import repository as repo
from domains.archive.engines.clustering.registry import EngineName, PresetName, get_engine
from domains.archive.models import ArchiveDocument, ArchiveDocumentTag, ArchiveTag, DomainStopwords, DomainSynonyms
from domains.archive.schemas import ArchiveTagDTO


class TagService:
    """
    Serviço de domínio responsável por auditar, higienizar e unificar
    a taxonomia e as tags na camada Archive.
    """

    def __init__(self, db: Session):
        self.db = db

    def extract_and_clean_tags(self, indexing_points: str | None) -> list[ArchiveTagDTO]:
        """
        Lê os pontos de indexação brutos (separados por vírgula), aplica
        o dicionário de stopwords do banco de dados e retorna os contratos validados.
        """
        if not indexing_points:
            return []

        # Busca as stopwords ativas diretamente do banco
        stopwords = set(self.db.scalars(select(DomainStopwords.word)).all())

        tags_brutas = indexing_points.split(",")
        tags_limpas = set()

        for tag in tags_brutas:
            tag = tag.strip().lower()

            for junk in stopwords:
                # Usa regex word boundaries (\b) para não apagar pedaços de palavras
                tag = re.sub(rf"\b{junk}\b", "", tag).strip()

            tag = re.sub(r"\s+", " ", tag)

            if 2 < len(tag) <= 100:
                tags_limpas.add(tag)
            elif len(tag) > 100:
                logger.warning(f"⚠️ Tag ignorada por ser muito longa: '{tag[:50]}...'")

        return [
            ArchiveTagDTO(name=tag_name, macro_category_id=None, ai_confidence_score=None) for tag_name in tags_limpas
        ]

    def purge_stopwords(self) -> int:
        """
        Varre a tabela de tags e apaga graciosamente qualquer tag que bata
        exatamente com a lista oficial de stopwords.

        Returns:
            int: O número de tags apagadas.
        """

        stopwords_clean = set(self.db.scalars(select(DomainStopwords.word)).all())
        if not stopwords_clean:
            return 0

        junk_tags = self.db.scalars(select(ArchiveTag).where(func.lower(ArchiveTag.name).in_(stopwords_clean))).all()

        if not junk_tags:
            return 0

        qtd_deleted = len(junk_tags)

        for tag in junk_tags:
            self.db.delete(tag)

        self.db.commit()
        return qtd_deleted

    def get_tag_relevance_count(self, limit: int = 30) -> Sequence[Row[tuple[str, int]]]:
        """
        Conta quantas vezes cada tag aparece associada a um documento no acervo.
        """
        stmt = (
            select(ArchiveTag.name, func.count(ArchiveDocumentTag.description_id).label("total_usos"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(text("total_usos DESC"))
            .limit(limit)
        )

        return self.db.execute(stmt).fetchall()

    def get_tag_relevance_tfidf(self, limit: int = 30):
        """
        Calcula a relevância global das tags usando a fórmula TF-IDF nativa no PostgreSQL.
        Penaliza tags genéricas que aparecem em todo o acervo e destaca termos específicos.
        """
        # 1. Pega o número total de documentos no acervo (N)
        total_docs = self.db.scalar(select(func.count(ArchiveDocument.description_id)))

        if not total_docs or total_docs == 0:
            return []

        # 2. Define os blocos matemáticos da Query
        df = func.count(ArchiveDocumentTag.description_id)  # Quantas vezes a tag foi usada

        # IDF = ln( Total de Documentos / Uso da Tag )
        # Usamos cast para Float para evitar divisão inteira no PostgreSQL
        idf = func.ln(total_docs / func.cast(df, Float))

        # Score Global = DF * IDF
        tfidf_score = df * idf

        # 3. Executa a query agrupando e ordenando pelo maior score
        stmt = (
            select(ArchiveTag.name, df.label("frequencia"), idf.label("peso_idf"), tfidf_score.label("score_tfidf"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(desc("score_tfidf"))
            .limit(limit)
        )

        # Retorna uma lista de tuplas estruturadas
        return self.db.execute(stmt).fetchall()

    def find_similar_tags(self, target_tag: str, threshold: float = 0.5) -> Sequence[Row[tuple[int, str, float]]]:
        """
        Busca tags com erros de digitação ou similaridade alta usando a extensão pg_trgm.
        """

        target_lower = target_tag.lower()
        similaridade = func.similarity(ArchiveTag.name, target_lower)

        stmt = (
            select(ArchiveTag.tag_id, ArchiveTag.name, similaridade.label("sim_score"))
            .where(similaridade >= threshold)
            # Ignora a própria palavra alvo
            .where(func.lower(ArchiveTag.name) != target_lower)
            .order_by(desc("sim_score"))
            .limit(15)
        )

        return self.db.execute(stmt).fetchall()

    def merge_tags(self, canonical_id: int, ids_to_merge: list[int]) -> tuple[int, int]:
        """
        Funde múltiplas tags incorretas numa tag canônica.
        1. Salva os nomes das tags descartadas como sinônimos da canônica.
        2. Transfere os vínculos de documentos.
        3. Apaga as tags erradas.

        Returns:
            tuple[int, int]: (Qtd de Documentos Atualizados, Qtd de Tags Apagadas)
        """
        if not ids_to_merge:
            return 0, 0

        # 1. Busca os nomes das tags que vão ser mescladas (futuros sinônimos)
        tags_mortas = self.db.scalars(select(ArchiveTag).where(ArchiveTag.tag_id.in_(ids_to_merge))).all()
        nomes_sinonimos = [t.name for t in tags_mortas]

        # 2. Transfere os Documentos de forma segura (Prevenção de Unique Constraint)
        # Busca todos os IDs de documentos que usavam as tags erradas
        docs_afetados = (
            self.db.execute(
                select(ArchiveDocumentTag.description_id).where(ArchiveDocumentTag.tag_id.in_(ids_to_merge))
            )
            .scalars()
            .all()
        )

        if docs_afetados:
            # Usamos set() para remover duplicidades se um mesmo documento tinha 2 tags erradas
            novos_vinculos = [{"description_id": doc_id, "tag_id": canonical_id} for doc_id in set(docs_afetados)]

            # Tenta inserir a tag canônica nesses documentos. Se o doc já tiver a tag, ignora silenciosamente.
            stmt_transfer = insert(ArchiveDocumentTag).values(novos_vinculos).on_conflict_do_nothing()
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
            stmt_syn = insert(DomainSynonyms).values(sinonimos_data).on_conflict_do_nothing()
            self.db.execute(stmt_syn)

        # 4. Limpeza Final
        # Apaga os vínculos associativos antigos (caso o banco não esteja com CASCADE configurado)
        self.db.execute(delete(ArchiveDocumentTag).where(ArchiveDocumentTag.tag_id.in_(ids_to_merge)))

        # Apaga as tags da tabela principal
        resultado_delete = self.db.execute(delete(ArchiveTag).where(ArchiveTag.tag_id.in_(ids_to_merge)))

        resultado_delete = cast(CursorResult, resultado_delete)
        return len(docs_afetados), resultado_delete.rowcount

    def suggest_macro_categories(
        self,
        source_type: Literal["tags", "documents"] = "tags",
        columns_to_extract: list[str] | None = None,
        engine_name: EngineName = "bertopic",
        preset: PresetName = "exploratorio_macro",
    ) -> dict[Any, Any]:
        """
        Extrai todas a tags do acervo e utiliza Inteligência Artificial
        (Clustering) para sugerir agrupamentos semânticos (Macro Categorias).
        """

        logger.info(f"🔍 Iniciando descoberta de tópicos com {engine_name} ({preset}) usando {source_type}...")

        if source_type == "tags":
            texts_to_analize = repo.fetch_tags_for_clustering(db=self.db)
        elif source_type == "documents":
            texts_to_analize = repo.fetch_documents_for_clustering(db=self.db, columns_to_extract=columns_to_extract)
        else:
            raise ValueError("O parâmetro 'source_type' deve ser 'tags' ou 'documents'.")

        if not texts_to_analize or len(texts_to_analize) < 10:
            logger.warning("⚠️ Textos insuficientes para formar clusters semânticos.")
            return {}

        engine = get_engine(engine_name, preset=preset)

        topics, topic_info_df = engine.discover_topics(list(texts_to_analize))

        results = {}

        # Formatação de Negócios
        for _, row in topic_info_df.iterrows():
            topic_id = row["Topic"]

            if topic_id == -1:
                continue

            # Cruza os IDs gerados com a lista de palavras enviadas para extrair amostras
            amostras = [texts_to_analize[i] for i, t in enumerate(topics) if t == topic_id]

            results[topic_id] = {
                "nome_sugerido": " - ".join(row["Representation"][:3]).title(),
                "volume_estimado": row["Count"],
                "amostras_reais": amostras[:10],
            }

        logger.info(f"🎯 Foram sugeridas {len(results)} Macro Categorias potenciais.")
        return results
