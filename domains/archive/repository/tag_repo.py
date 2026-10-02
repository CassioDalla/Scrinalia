from collections.abc import Sequence
from typing import cast

from sqlalchemy import CursorResult, Float, delete, desc, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from domains.archive.domain.normalization import normalize_stopword, normalize_synonym, normalize_tag
from domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentTag,
    ArchiveMacroCategory,
    ArchiveTag,
    DomainStopwords,
    DomainSynonyms,
)
from domains.archive.schemas import (
    ArchiveMacroCategoryEntityDTO,
    ArchiveTagDTO,
    SynonymCommand,
    TagIdentity,
    TagPairSimilarity,
    TagRelevanceCount,
    TagRelevanceIdf,
    TagSimilarity,
)


class TagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def fetch_tags_for_clustering(self) -> list[str]:
        """Fetches only unique tags that do not yet have a Macro Category."""
        stmt = select(ArchiveTag.name).where(ArchiveTag.macro_category_id.is_(None)).distinct()
        results = self.db.scalars(stmt).all()

        texts = [t for t in results if t and not t.replace(".", "").isdigit()]
        return texts

    def get_synonyms_mapping(self, words: list[str]) -> dict[str, int]:
        """
        Checks in the database whether any of the provided words is a known synonym.
        Returns a dictionary mapping: { 'synonym_name': ID_of_Canonical_Tag }
        """
        if not words:
            return {}

        words_clean = [normalize_tag(w) for w in words]

        stmt = select(DomainSynonyms.synonym_name, DomainSynonyms.canonical_tag_id).where(
            DomainSynonyms.category == "TAG", DomainSynonyms.synonym_name.in_(words_clean)
        )

        results = self.db.execute(stmt).all()
        return {row.synonym_name: row.canonical_tag_id for row in results}

    def get_or_create_tags(self, tags_list: list[ArchiveTagDTO]) -> list[int]:
        """
        Manages the dimension of tags and taxonomies of mDeBERTa.
        Ensures that identical terms (in lowercase) share the same ID in the database.
        """

        if not tags_list:
            return []

        insert_data = []
        names_to_search = []

        for t in tags_list:
            name_clean = normalize_tag(t.name)
            names_to_search.append(name_clean)
            insert_data.append(
                {
                    "name": name_clean,
                    "macro_category_id": t.macro_category_id,
                    "ai_confidence_score": t.ai_confidence_score,
                }
            )

        # 2. Performs the mass INSERT ignoring tags that already exist (thanks to the unique index on the 'name' column)
        stmt_insert = insert(ArchiveTag).values(insert_data).on_conflict_do_nothing(index_elements=["name"])
        self.db.execute(stmt_insert)

        # 3. In a SINGLE select, fetches all IDs (both the newly created and the already existing ones)
        stmt_select = select(ArchiveTag.tag_id).where(ArchiveTag.name.in_(names_to_search))

        return list(self.db.scalars(stmt_select).all())

    def save_stopwords(self, words_list: list[str]) -> int:
        """
        Inserts a list of words into the stopwords table in batch.
        Returns the exact number of new stopwords inserted.
        """
        if not words_list:
            return 0

        clean_words = [{"word": normalize_stopword(w)} for w in words_list if w.strip()]

        if not clean_words:
            return 0

        stmt = insert(DomainStopwords).values(clean_words).on_conflict_do_nothing()

        result = cast(CursorResult, self.db.execute(stmt))
        return result.rowcount

    def get_stopwords(self) -> set[str]:
        """
        Retrieves all domain stopwords registered in the database.
        Returns a set (Set) of stopwords

        Args:
            db (Session): Active SQLAlchemy session.

        Returns:
            set[str]: Set containing all stopwords in lowercase letters.
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

    def purge_tags_by_stopwords(self, stopwords: set[str]) -> int:
        """Mass deletes all tags that match the stopwords list."""
        stmt = delete(ArchiveTag).where(func.lower(ArchiveTag.name).in_(stopwords))
        result = self.db.execute(stmt)
        return cast(CursorResult, result).rowcount

    def get_relevance_count(self, limit: int) -> Sequence[TagRelevanceCount]:
        stmt = (
            select(ArchiveTag.name, func.count(ArchiveDocumentTag.description_id).label("total_usage"))
            .join(ArchiveDocumentTag, ArchiveTag.tag_id == ArchiveDocumentTag.tag_id)
            .group_by(ArchiveTag.tag_id, ArchiveTag.name)
            .order_by(text("total_usage DESC"))
            .limit(limit)
        )
        return [TagRelevanceCount.model_validate(row) for row in self.db.execute(stmt).all()]

    def get_relevance_tfidf(self, limit: int) -> Sequence[TagRelevanceIdf]:
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
        return [TagRelevanceIdf.model_validate(row) for row in self.db.execute(stmt).all()]

    def find_similar(self, target_lower: str, threshold: float) -> Sequence[TagSimilarity]:
        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})
        similarity = func.similarity(ArchiveTag.name, target_lower)
        stmt = (
            select(ArchiveTag.tag_id, ArchiveTag.name, similarity.label("similarity"))
            .where(ArchiveTag.name.op("%")(target_lower))
            .where(func.lower(ArchiveTag.name) != target_lower)
            .order_by(desc("similarity"))
            .limit(15)
        )
        return [TagSimilarity.model_validate(row) for row in self.db.execute(stmt).all()]

    def find_all_similar_pairs(self, threshold: float) -> Sequence[TagPairSimilarity]:
        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})
        Tag1 = aliased(ArchiveTag)
        Tag2 = aliased(ArchiveTag)
        similarity = func.similarity(Tag1.name, Tag2.name)
        stmt = (
            select(
                Tag1.tag_id.label("id_1"),
                Tag1.name.label("name_1"),
                Tag2.tag_id.label("id_2"),
                Tag2.name.label("name_2"),
                similarity.label("sim_score"),
            )
            # The Join ensuring that only unique combinations are tested and it ignores itself
            .join(Tag2, Tag1.tag_id < Tag2.tag_id)
            # Only compares tags that have up to 3 letters of difference in length
            .where(func.abs(func.length(Tag1.name) - func.length(Tag2.name)) <= 3)
            .where(Tag1.name.op("%")(Tag2.name))
            .order_by(desc("sim_score"), Tag1.name)
        )
        return [TagPairSimilarity.model_validate(row) for row in self.db.execute(stmt).all()]

    # --- Auxiliary Methods for the Tag Merge ---

    def get_by_id(self, tag_id: int) -> TagIdentity | None:
        obj = self.db.scalar(select(ArchiveTag).where(ArchiveTag.tag_id == tag_id))
        return TagIdentity.model_validate(obj) if obj else None

    def get_by_ids(self, tag_ids: list[int]) -> Sequence[TagIdentity]:
        objs = self.db.scalars(select(ArchiveTag).where(ArchiveTag.tag_id.in_(tag_ids))).all()
        return [TagIdentity.model_validate(obj) for obj in objs]

    def get_document_ids_by_tags(self, tag_ids: list[int]) -> Sequence[str]:
        return self.db.scalars(
            select(ArchiveDocumentTag.description_id).where(ArchiveDocumentTag.tag_id.in_(tag_ids))
        ).all()

    def link_documents_to_tag(self, doc_ids: set[str], target_tag_id: int) -> None:
        new_links = [{"description_id": doc_id, "tag_id": target_tag_id} for doc_id in doc_ids]
        stmt = insert(ArchiveDocumentTag).values(new_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def link_tags_to_document(self, description_id: str, tag_ids: list[int]) -> None:
        """Links multiple tags to a single document (Used occasionally)."""
        if not tag_ids:
            return

        new_links = [{"description_id": description_id, "tag_id": t_id} for t_id in set(tag_ids)]
        stmt = insert(ArchiveDocumentTag).values(new_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def bulk_link_tags(self, links_data: list[dict]) -> None:
        """
        Optimization for Batch Ingestion (Workers).
        Inserts thousands of N:N links in a single transaction.
        Receives: [{"description_id": "doc1", "tag_id": 1}, ...]
        """
        if not links_data:
            return

        # Converts to tuples and then back to dict to remove exact duplicates
        # sent in the same batch, preventing unnecessary locks
        unique_links = [dict(t) for t in {tuple(d.items()) for d in links_data}]

        stmt = insert(ArchiveDocumentTag).values(unique_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def create_synonyms(self, synonyms_data: list[SynonymCommand]) -> None:
        rows = [
            {
                "synonym_name": normalize_synonym(item.synonym_name),
                "category": item.category,
                "canonical_tag_id": item.canonical_tag_id,
                "canonical_entity_id": item.canonical_entity_id,
            }
            for item in synonyms_data
        ]
        stmt = insert(DomainSynonyms).values(rows).on_conflict_do_nothing()
        self.db.execute(stmt)

    def delete_tags(self, tag_ids: list[int]) -> int:
        self.db.execute(delete(ArchiveDocumentTag).where(ArchiveDocumentTag.tag_id.in_(tag_ids)))
        result = self.db.execute(delete(ArchiveTag).where(ArchiveTag.tag_id.in_(tag_ids)))
        return cast(CursorResult, result).rowcount
