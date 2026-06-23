import re
from collections.abc import Sequence
from typing import Literal, cast

from sqlalchemy import CursorResult, Float, delete, desc, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from core.logger import logger
from domains.archive import repository as repo
from domains.archive.exceptions import InvalidMergeTagError, InvalidParam
from domains.archive.models import ArchiveDocument, ArchiveDocumentTag, ArchiveTag, DomainStopwords, DomainSynonyms
from domains.archive.schemas.schemas import ArchiveTagDTO
from domains.archive.schemas.tag_schema import (
    MergeResponse,
    TagPairSimilarity,
    TagRelevanceCount,
    TagRelevanceIdf,
    TagSimilarity,
)


class TagService:
    """
    Serviço de domínio responsável por auditar, higienizar e unificar
    a taxonomia e as tags na camada Archive.
    """

    def __init__(self, db: Session):
        self.db = db
        self._stopwords_regex = None

    def _get_stopwords_regex(self) -> re.Pattern:
        """
        Busca as stopwords no banco apenas uma vez e compila um super-regex.
        """
        if self._stopwords_regex is None:
            # Puxa do banco
            stopwords = repo.get_stopwords(self.db)

            if stopwords:
                # Escapa os caracteres especiais das stopwords (caso haja algum '+', '.', etc)
                # e junta tudo com o pipe '|' (Operador OR)
                words = "|".join(re.escape(w) for w in stopwords)
                pattern = rf"\b({words})\b"

                # Compila o regex com a flag de ignorar maiúsculas/minúsculas
                self._stopwords_regex = re.compile(pattern, flags=re.IGNORECASE)
            else:
                # Se o banco estiver vazio, cria um regex que nunca dá match
                self._stopwords_regex = re.compile(r"a^")

        return self._stopwords_regex

    def extract_and_clean_tags(self, indexing_points: str | None) -> list[ArchiveTagDTO]:
        """
        Lê os pontos de indexação brutos (separados por vírgula), aplica
        o dicionário de stopwords do banco de dados e retorna os contratos validados.
        """
        if not indexing_points:
            return []

        # Busca as stopwords ativas diretamente do banco
        regex_stopwords = self._get_stopwords_regex()

        tags_brutas = indexing_points.split(",")
        tags_limpas = set()

        for tag in tags_brutas:
            tag = tag.strip().lower()

            tag = regex_stopwords.sub("", tag).strip()

            tag = re.sub(r"\s+", " ", tag)

            if 2 < len(tag) <= 100:
                tags_limpas.add(tag)
            elif len(tag) > 100:
                logger.warning(f"⚠️ Tag ignorada por ser muito longa: '{tag[:50]}...'")

        return [
            ArchiveTagDTO(name=tag_name, macro_category_id=None, ai_confidence_score=None) for tag_name in tags_limpas
        ]

    def process_worker_tags(self, dtos_from_worker: list[ArchiveTagDTO]) -> list[int]:
        """
        Pipeline de negócio: Verifica sinônimos e roteia para gravação.
        Retorna a lista final de IDs (canônicos ou recém-criados) para vincular ao documento.
        """
        if not dtos_from_worker:
            return []

        # 1. Extrai apenas os nomes em minúsculas para checar os sinônimos no banco
        names_to_search = [dto.name.strip().lower() for dto in dtos_from_worker]

        # 2. Busca o mapeamento no Repositório (Retorna algo como: {"prefeiruta": 45, "parques": 12})
        mapa_sinonimos = repo.get_synonyms_mapping(self.db, names_to_search)

        ids_finais_para_o_documento = []
        dtos_para_criar = []

        # 3. O Roteamento de Regra de Negócio (A malha fina)
        for dto in dtos_from_worker:
            nome_normalizado = dto.name.strip().lower()

            if nome_normalizado in mapa_sinonimos:
                # É um sinônimo conhecido! Descartamos a DTO e usamos o ID da Tag Canônica
                id_canonico = mapa_sinonimos[nome_normalizado]
                ids_finais_para_o_documento.append(id_canonico)
            else:
                # É uma tag nova ou legítima. Vai para a fila de persistência.
                dtos_para_criar.append(dto)

        # 4. Envia para o repositório de criação APENAS as tags que não eram sinônimos
        if dtos_para_criar:
            ids_novos_ou_existentes = repo.get_or_create_tags(self.db, dtos_para_criar)
            ids_finais_para_o_documento.extend(ids_novos_ou_existentes)

        # 5. Retorna um set convertido em lista para garantir que o mesmo documento
        # não receba o mesmo ID de tag duas vezes (ex: se "parque" e "parques" vierem no mesmo documento)
        return list(set(ids_finais_para_o_documento))

    def save_new_stopwords(self, word_list: list[str]) -> int:
        return repo.save_stopwords(self.db, word_list)

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

    def get_tag_relevance_count(self, limit: int = 30) -> Sequence[TagRelevanceCount]:
        """
        Conta quantas vezes cada tag aparece associada a um documento no acervo.
        """
        stmt = (
            select(ArchiveTag.name, func.count(ArchiveDocumentTag.description_id).label("total_usage"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(text("total_usage DESC"))
            .limit(limit)
        )

        results = self.db.execute(stmt).fetchall()

        return [TagRelevanceCount.model_validate(r) for r in results]

    def get_tag_relevance_tfidf(self, limit: int = 30) -> Sequence[TagRelevanceIdf]:
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
            select(ArchiveTag.name, df.label("frequency"), idf.label("weight_idf"), tfidf_score.label("score_tfidf"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(desc("score_tfidf"))
            .limit(limit)
        )
        results = self.db.execute(stmt).fetchall()

        return [TagRelevanceIdf.model_validate(r) for r in results]

    def find_similar_tags(self, target_tag: str, threshold: float = 0.5) -> Sequence[TagSimilarity]:
        """
        Busca tags com erros de digitação ou similaridade alta usando a extensão pg_trgm.
        """
        if not target_tag:
            raise InvalidParam("O parametro 'target_tag'é obrigatório")

        self.db.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {threshold}"))

        target_lower = target_tag.lower()
        similaridade = func.similarity(ArchiveTag.name, target_lower)

        stmt = (
            select(ArchiveTag.tag_id, ArchiveTag.name, similaridade.label("similarity"))
            .where(ArchiveTag.name.op("%")(target_lower))
            # Ignora a própria palavra alvo
            .where(func.lower(ArchiveTag.name) != target_lower)
            .order_by(desc("similarity"))
            .limit(15)
        )
        results = self.db.execute(stmt).fetchall()
        return [TagSimilarity.model_validate(r) for r in results]

    def find_all_similar_tag_pairs(self, threshold: float = 0.65) -> Sequence[TagPairSimilarity]:
        """
        Varre o acervo e cruza todas as tags entre si para encontrar
        pares que sejam muito parecidos (potenciais duplicações).
        """
        # 1. Configura o threshold nativo do PostgreSQL apenas para esta transação.
        self.db.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {threshold}"))

        # Cria os alias para o Self Join
        Tag1 = aliased(ArchiveTag)
        Tag2 = aliased(ArchiveTag)

        # Prepara o cálculo de similaridade
        similaridade = func.similarity(Tag1.name, Tag2.name)

        stmt = (
            select(
                Tag1.tag_id.label("id_1"),
                Tag1.name.label("name_1"),
                Tag2.tag_id.label("id_2"),
                Tag2.name.label("name_2"),
                similaridade.label("sim_score"),
            )
            # O Join garantindo que só testa combinações únicas e ignora a si mesma
            .join(Tag2, Tag1.tag_id < Tag2.tag_id)
            # 2. HACK DE PERFORMANCE: Só compara tags que tenham até 3 letras de diferença no tamanho
            .where(func.abs(func.length(Tag1.name) - func.length(Tag2.name)) <= 3)
            # 3. O SEGREDO: O operador % é a única coisa que ativa o Índice GIN!
            .where(Tag1.name.op("%")(Tag2.name))
            .order_by(desc("sim_score"), Tag1.name)
        )

        results = self.db.execute(stmt).fetchall()

        return [TagPairSimilarity.model_validate(r) for r in results]

    def merge_tags(self, canonical_id: int, ids_to_merge: list[int]) -> MergeResponse:
        """
        Funde múltiplas tags incorretas numa tag canônica.
        1. Salva os nomes das tags descartadas como sinônimos da canônica.
        2. Transfere os vínculos de documentos.
        3. Apaga as tags erradas.

        Returns:
            tuple[int, int]: (Qtd de Documentos Atualizados, Qtd de Tags Apagadas)
        """
        if not ids_to_merge:
            raise InvalidParam("A lista de tags para mesclar não pode estar vazia.")

        if canonical_id in ids_to_merge:
            raise InvalidMergeTagError("O ID da tag canônica não pode estar na lista de exclusão.")

        # Garante que a tag canônica realmente existe
        canonical_exists = self.db.scalar(select(ArchiveTag.tag_id).where(ArchiveTag.tag_id == canonical_id))
        if not canonical_exists:
            raise InvalidParam(f"A tag canônica informada (ID {canonical_id}) não existe no acervo.")

        documents_updated: int = 0
        tags_deleted: int = 0
        try:
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
            documents_updated = len(docs_afetados)
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
            tags_deleted = resultado_delete.rowcount

            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(e)
            raise InvalidMergeTagError("Falha interna ao tentar mesclar as tags no acervo.") from e

        return MergeResponse(documents_updated=documents_updated, tags_deleted=tags_deleted)

    def get_text_to_suggest_macro_category(
        self,
        source_type: Literal["tags", "documents"] = "tags",
        columns_to_extract: list[str] | None = None,
    ) -> list[str]:
        """
        Extrai todas a tags do acervo e utiliza Inteligência Artificial
        (Clustering) para sugerir agrupamentos semânticos (Macro Categorias).
        """

        logger.info(f"🔍 Iniciando descoberta de tópicos usando source_type:{source_type}...")

        if source_type not in ["tags", "documents"]:
            raise InvalidParam("O parâmetro 'source_type' deve ser obrigatoriamente 'tags' ou 'documents'.")

        if source_type == "tags":
            texts_to_analize = repo.fetch_tags_for_clustering(db=self.db)
        elif source_type == "documents":
            texts_to_analize = repo.fetch_documents_for_clustering(db=self.db, columns_to_extract=columns_to_extract)
        else:
            raise InvalidParam("O parâmetro 'source_type' deve ser 'tags' ou 'documents'.")

        return texts_to_analize

    # TODO Pensar em como fazer isso. Tirar as entidades conhecidas das tags ou não. Tags precisam ser classiicadas em assuntos.
    def purge_entities_from_tags(self):
        pass
