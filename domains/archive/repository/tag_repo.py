from collections.abc import Sequence
from typing import cast

from sqlalchemy import CursorResult, Float, Row, delete, desc, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentTag,
    ArchiveMacroCategory,
    ArchiveTag,
    DomainStopwords,
    DomainSynonyms,
)
from domains.archive.schemas import ArchiveMacroCategoryEntityDTO, ArchiveTagDTO


class TagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def fetch_tags_for_clustering(self) -> list[str]:
        """Busca apenas tags únicas que ainda não têm Macro Categoria."""
        stmt = select(ArchiveTag.name).where(ArchiveTag.macro_category_id.is_(None)).distinct()
        results = self.db.scalars(stmt).all()

        texts = [t for t in results if t and not t.replace(".", "").isdigit()]
        return texts

    def get_synonyms_mapping(self, words: list[str]) -> dict[str, int]:
        """
        Busca no banco se alguma das palavras fornecidas é um sinônimo conhecido.
        Retorna um dicionário mapeando: { 'nome_do_sinonimo': ID_da_Tag_Canonica }
        """
        if not words:
            return {}

        words_clean = [w.strip().lower() for w in words]

        stmt = select(DomainSynonyms.synonym_name, DomainSynonyms.canonical_tag_id).where(
            DomainSynonyms.category == "TAG", DomainSynonyms.synonym_name.in_(words_clean)
        )

        resultados = self.db.execute(stmt).all()
        return {row.synonym_name: row.canonical_tag_id for row in resultados}

    def get_or_create_tags(self, tags_list: list[ArchiveTagDTO]) -> list[int]:
        """
        Gerencia a dimensão de tags e taxonomias do mDeBERTa.
        Garante que termos idênticos (em minúsculas) partilhem o mesmo ID no banco.
        """

        if not tags_list:
            return []

        insert_data = []
        names_to_search = []

        for t in tags_list:
            name_clean = t.name.strip().lower()
            names_to_search.append(name_clean)
            insert_data.append(
                {
                    "name": name_clean,
                    "macro_category_id": t.macro_category_id,
                    "ai_confidence_score": t.ai_confidence_score,
                }
            )

        # 2. Faz o INSERT massivo ignorando as tags que já existem (graças ao índice único na coluna 'name')
        stmt_insert = insert(ArchiveTag).values(insert_data).on_conflict_do_nothing(index_elements=["name"])
        self.db.execute(stmt_insert)

        # 3. Num ÚNICO select, busca todos os IDs (dos que acabaram de ser criados e dos que já existiam)
        stmt_select = select(ArchiveTag.tag_id).where(ArchiveTag.name.in_(names_to_search))

        return list(self.db.scalars(stmt_select).all())

    def save_stopwords(self, words_list: list[str]) -> int:
        """
        Insere uma lista de palavras na tabela de stopwords em lote.
        Retorna a quantidade exata de novas stopwords inseridas.
        """
        if not words_list:
            return 0

        clean_words = [{"word": w.strip().lower()} for w in words_list if w.strip()]

        if not clean_words:
            return 0

        stmt = insert(DomainStopwords).values(clean_words).on_conflict_do_nothing()

        result = cast(CursorResult, self.db.execute(stmt))
        return result.rowcount

    def get_stopwords(self) -> set[str]:
        """
        Recupera todas as stopwords de domínio cadastradas no banco de dados.
        Retorna um conjunto (Set) de stopwords

        Args:
            db (Session): Sessão ativa do SQLAlchemy.

        Returns:
            set[str]: Conjunto contendo todas as stopwords em letras minúsculas.
        """
        stmt = select(DomainStopwords.word)
        results = self.db.scalars(stmt).all()
        return set(results)

    def get_macro_categories(self) -> list[ArchiveMacroCategoryEntityDTO]:

        stmt = select(
            ArchiveMacroCategory.category_id,
            ArchiveMacroCategory.name,
            ArchiveMacroCategory.description,
            ArchiveMacroCategory.is_active,
        )

        results = self.db.execute(stmt).mappings().all()
        return [ArchiveMacroCategoryEntityDTO.model_validate(r) for r in results]

    # TODO
    def create_macro_category(self, m_category: ArchiveMacroCategoryEntityDTO): ...

    # TODO pensar na melhor forma de fazer isso e nos args. Receber a model do banco, DTOS ou listas simples de ids
    def link_to_macro_category(self, tags_ids: list[int], m_category_id: int): ...

    def purge_tags_by_stopwords(self, stopwords: set[str]) -> int:
        """Deleta em massa todas as tags que coincidem com a lista de stopwords."""
        stmt = delete(ArchiveTag).where(func.lower(ArchiveTag.name).in_(stopwords))
        result = self.db.execute(stmt)
        return cast(CursorResult, result).rowcount

    def get_relevance_count(self, limit: int) -> Sequence[Row]:
        stmt = (
            select(ArchiveTag.name, func.count(ArchiveDocumentTag.description_id).label("total_usage"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(text("total_usage DESC"))
            .limit(limit)
        )
        return self.db.execute(stmt).all()

    def get_relevance_tfidf(self, limit: int) -> Sequence[Row]:
        total_docs = self.db.scalar(select(func.count(ArchiveDocument.description_id)))
        if not total_docs or total_docs == 0:
            return []

        df = func.count(ArchiveDocumentTag.description_id)
        idf = func.ln(total_docs / func.cast(df, Float))
        tfidf_score = df * idf

        stmt = (
            select(ArchiveTag.name, df.label("frequency"), idf.label("weight_idf"), tfidf_score.label("score_tfidf"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(desc("score_tfidf"))
            .limit(limit)
        )
        return self.db.execute(stmt).all()

    def find_similar(self, target_lower: str, threshold: float) -> Sequence[Row]:
        self.db.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {threshold}"))
        similaridade = func.similarity(ArchiveTag.name, target_lower)
        stmt = (
            select(ArchiveTag.tag_id, ArchiveTag.name, similaridade.label("similarity"))
            .where(ArchiveTag.name.op("%")(target_lower))
            .where(func.lower(ArchiveTag.name) != target_lower)
            .order_by(desc("similarity"))
            .limit(15)
        )
        return self.db.execute(stmt).all()

    def find_all_similar_pairs(self, threshold: float) -> Sequence[Row]:
        self.db.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {threshold}"))
        Tag1 = aliased(ArchiveTag)
        Tag2 = aliased(ArchiveTag)
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
            # Só compara tags que tenham até 3 letras de diferença no tamanho
            .where(func.abs(func.length(Tag1.name) - func.length(Tag2.name)) <= 3)
            .where(Tag1.name.op("%")(Tag2.name))
            .order_by(desc("sim_score"), Tag1.name)
        )
        return self.db.execute(stmt).all()

    # --- Métodos Auxiliares para o Merge de Tags ---

    def get_by_id(self, tag_id: int) -> ArchiveTag | None:
        return self.db.scalar(select(ArchiveTag).where(ArchiveTag.tag_id == tag_id))

    def get_by_ids(self, tag_ids: list[int]) -> Sequence[ArchiveTag]:
        return self.db.scalars(select(ArchiveTag).where(ArchiveTag.tag_id.in_(tag_ids))).all()

    def get_document_ids_by_tags(self, tag_ids: list[int]) -> Sequence[str]:
        return self.db.scalars(
            select(ArchiveDocumentTag.description_id).where(ArchiveDocumentTag.tag_id.in_(tag_ids))
        ).all()

    def link_documents_to_tag(self, doc_ids: set[str], target_tag_id: int) -> None:
        novos_vinculos = [{"description_id": doc_id, "tag_id": target_tag_id} for doc_id in doc_ids]
        stmt = insert(ArchiveDocumentTag).values(novos_vinculos).on_conflict_do_nothing()
        self.db.execute(stmt)

    def link_tags_to_document(self, description_id: str, tag_ids: list[int]) -> None:
        """Vincula múltiplas tags a um único documento (Usado pontualmente)."""
        if not tag_ids:
            return

        novos_vinculos = [{"description_id": description_id, "tag_id": t_id} for t_id in set(tag_ids)]
        stmt = insert(ArchiveDocumentTag).values(novos_vinculos).on_conflict_do_nothing()
        self.db.execute(stmt)

    def bulk_link_tags(self, links_data: list[dict]) -> None:
        """
        Otimização para Ingestão em Lote (Workers).
        Insere milhares de vínculos N:N numa única transação.
        Recebe: [{"description_id": "doc1", "tag_id": 1}, ...]
        """
        if not links_data:
            return

        # Converte para tuplas e depois para dict novamente para remover duplicidades
        # exatas enviadas no mesmo lote, prevenindo trancamentos desnecessários (locks)
        unique_links = [dict(t) for t in {tuple(d.items()) for d in links_data}]

        stmt = insert(ArchiveDocumentTag).values(unique_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def create_synonyms(self, synonyms_data: list[dict]) -> None:
        stmt = insert(DomainSynonyms).values(synonyms_data).on_conflict_do_nothing()
        self.db.execute(stmt)

    def delete_tags(self, tag_ids: list[int]) -> int:
        self.db.execute(delete(ArchiveDocumentTag).where(ArchiveDocumentTag.tag_id.in_(tag_ids)))
        result = self.db.execute(delete(ArchiveTag).where(ArchiveTag.tag_id.in_(tag_ids)))
        return cast(CursorResult, result).rowcount
