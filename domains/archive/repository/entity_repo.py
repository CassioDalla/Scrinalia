from collections.abc import Sequence
from typing import Literal, cast

from sqlalchemy import CursorResult, Row, delete, desc, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from domains.archive.exceptions import InvalidParam
from domains.archive.models import (
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveTag,
    DomainStopwords,
    DomainSynonyms,
    StopwordsScope,
)
from domains.archive.schemas.entity_schema import ArchiveEntityDTO


class EntityRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, entity_id: int) -> ArchiveEntity | None:
        return self.db.scalar(select(ArchiveEntity).where(ArchiveEntity.entity_id == entity_id))

    def get_by_ids(self, entity_ids: list[int]) -> Sequence[ArchiveEntity]:
        if not entity_ids:
            return []
        return self.db.scalars(select(ArchiveEntity).where(ArchiveEntity.entity_id.in_(entity_ids))).all()

    def find_similar(
        self, target_name: str, entity_type: Literal["ORG", "PER", "LOC"] | None = None, threshold: float = 0.5
    ) -> Sequence[Row]:
        """
        Searches for entities with typos or high similarity using the pg_trgm extension.
        Also returns the 'entity_type' to help the user decide whether the merge makes sense.
        """

        if not target_name:
            raise InvalidParam("O parametro 'target_tag'é obrigatório")

        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})

        target_lower = target_name.lower()
        similarity = func.similarity(ArchiveEntity.name, target_lower)

        stmt = (
            select(
                ArchiveEntity.entity_id, ArchiveEntity.name, ArchiveEntity.entity_type, similarity.label("similarity")
            )
            .where(ArchiveEntity.name.op("%")(target_lower))
            .where(func.lower(ArchiveEntity.name) != target_lower)
        )

        if entity_type:
            stmt = stmt.where(ArchiveEntity.entity_type == entity_type)

        stmt = stmt.order_by(desc("similarity")).limit(15)

        return self.db.execute(stmt).fetchall()

    def find_all_similar_pairs(self, threshold: float = 0.65) -> Sequence[Row]:
        """
        Scans the collection and cross-references all entities with each other to find
        pairs that are very similar (potential duplications or NER errors).
        """
        # 1. Configures PostgreSQL's native threshold only for this transaction.
        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})

        # Creates the aliases for the Self Join
        Entity1 = aliased(ArchiveEntity)
        Entity2 = aliased(ArchiveEntity)

        # Prepares the similarity calculation
        similarity = func.similarity(Entity1.name, Entity2.name)

        stmt = (
            select(
                Entity1.entity_id.label("id_1"),
                Entity1.name.label("name_1"),
                Entity1.entity_type.label("type_1"),
                Entity2.entity_id.label("id_2"),
                Entity2.name.label("name_2"),
                Entity2.entity_type.label("type_2"),
                similarity.label("similarity"),
            )
            # The Join ensuring that only unique combinations are tested (A with B) and mirrored ones (B with A) are ignored
            .join(Entity2, Entity1.entity_id < Entity2.entity_id)
            # 2. PERFORMANCE HACK: Only compares entities that have up to 3 letters of difference in length
            .where(func.abs(func.length(Entity1.name) - func.length(Entity2.name)) <= 3)
            # 3. THE SECRET: The % operator is the only thing that activates the GIN Index!
            .where(Entity1.name.op("%")(Entity2.name))
            .order_by(desc("similarity"), Entity1.name)
        )

        return self.db.execute(stmt).all()

    def get_cross_domain_conflicts(self, threshold: float) -> Sequence[Row]:
        """Searches for conflicts where the Tag name is identical or very similar to the Entity's."""
        self.db.execute(text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold})

        sim_score = func.similarity(ArchiveTag.name, ArchiveEntity.name)

        stmt = (
            select(
                ArchiveTag.tag_id,
                ArchiveTag.name.label("tag_name"),
                ArchiveEntity.entity_id,
                ArchiveEntity.name.label("entity_name"),
                ArchiveEntity.entity_type,
                sim_score.label("similarity"),
            )
            .join(
                ArchiveEntity,
                ArchiveTag.name.op("%")(ArchiveEntity.name)
                | (func.lower(ArchiveTag.name) == func.lower(ArchiveEntity.name)),
            )
            .order_by(desc("similarity"))
        )
        return self.db.execute(stmt).all()

    def resolve_cross_domain_conflict(self, winner: Literal["TAG", "ENTITY"], tag_id: int, entity_id: int) -> int:
        """
        Transfers the documents to the winner and deletes the loser atomically and
        adds the loser's name to the blacklist of its respective domain.
        Returns the number of documents transferred.
        """
        transferred_docs = 0

        if winner == "TAG":
            entity_name = self.db.scalar(select(ArchiveEntity.name).where(ArchiveEntity.entity_id == entity_id))

            # Fetches the Entity's docs and moves them to the Tag
            stmt_docs = select(ArchiveDocumentEntity.description_id).where(ArchiveDocumentEntity.entity_id == entity_id)
            doc_ids = self.db.scalars(stmt_docs).all()

            if doc_ids:
                new_links = [{"description_id": d, "tag_id": tag_id} for d in doc_ids]
                stmt_insert = insert(ArchiveDocumentTag).values(new_links).on_conflict_do_nothing()
                self.db.execute(stmt_insert)
                transferred_docs = len(doc_ids)

            self.db.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id == entity_id))

            if entity_name:
                stmt_stopword = (
                    insert(DomainStopwords)
                    .values(word=entity_name.lower().strip(), word_scope=StopwordsScope.ENTITY)
                    .on_conflict_do_nothing()
                )
                self.db.execute(stmt_stopword)

        elif winner == "ENTITY":
            tag_name = self.db.scalar(select(ArchiveTag.name).where(ArchiveTag.tag_id == tag_id))

            # Fetches the Tag's docs and moves them to the Entity
            stmt_docs = select(ArchiveDocumentTag.description_id).where(ArchiveDocumentTag.tag_id == tag_id)
            doc_ids = self.db.scalars(stmt_docs).all()

            if doc_ids:
                new_links = [{"description_id": d, "entity_id": entity_id} for d in doc_ids]
                stmt_insert = insert(ArchiveDocumentEntity).values(new_links).on_conflict_do_nothing()
                self.db.execute(stmt_insert)
                transferred_docs = len(doc_ids)

            self.db.execute(delete(ArchiveTag).where(ArchiveTag.tag_id == tag_id))

            if tag_name:
                stmt_stopword = (
                    insert(DomainStopwords)
                    .values(word=tag_name.lower().strip(), word_scope=StopwordsScope.TAG)
                    .on_conflict_do_nothing()
                )
                self.db.execute(stmt_stopword)

        return transferred_docs

    # --- Ingestion and NER Methods ---

    def get_ner_synonyms_rules(self) -> list[dict]:
        """
        Loads the semantic normalization rules exclusive to the NER pipeline (spaCy).
        Ignores TAG synonyms, returning only mappings to Canonical Entities.
        """

        stmt = (
            select(DomainSynonyms.synonym_name, DomainSynonyms.category, ArchiveEntity.name.label("canonical_entity"))
            .join(ArchiveEntity, DomainSynonyms.canonical_entity_id == ArchiveEntity.entity_id)
            .where(DomainSynonyms.category.in_(["ORG", "LOC", "PER"]))
        )

        results = self.db.execute(stmt).all()

        return [
            {"pattern": row.synonym_name, "label": row.category, "canonical_name": row.canonical_entity}
            for row in results
        ]

    def get_or_create_entities(self, entities_list: list[ArchiveEntityDTO]) -> list[int]:
        """
        Manages the entity dimension (NER).

        Receives a list of People, Organizations or Locations identified by the AI.
        Uses ON CONFLICT DO NOTHING to guarantee uniqueness by name.

        Returns:
            list[int]: List of IDs (Primary Keys) of the entities ready for linking.
        """

        if not entities_list:
            return []

        # 1. Prepares the list of dictionaries for the mass INSERT.
        # Names are normalized to lowercase (mirroring the Tag dimension) so that
        # "Curitiba" and "curitiba" resolve to the same canonical entity.
        insert_data = []
        names_to_search = []

        for ent in entities_list:
            name_clean = ent.name.strip().lower()
            names_to_search.append(name_clean)
            insert_data.append({"name": name_clean, "entity_type": ent.entity_type})

        # 2. Performs the mass INSERT ignoring entities that already exist (unique index on 'name')
        stmt_insert = insert(ArchiveEntity).values(insert_data).on_conflict_do_nothing(index_elements=["name"])
        self.db.execute(stmt_insert)

        # 3. In a SINGLE select, fetches all IDs (both the newly created and the already existing ones)
        stmt_select = select(ArchiveEntity.entity_id).where(ArchiveEntity.name.in_(names_to_search))

        return list(self.db.scalars(stmt_select).all())

    # --- Methods for the Merge ---

    def get_document_ids_by_entities(self, entity_ids: list[int]) -> Sequence[str]:
        stmt = select(ArchiveDocumentEntity.description_id).where(ArchiveDocumentEntity.entity_id.in_(entity_ids))
        return self.db.scalars(stmt).all()

    def link_documents_to_entity(self, doc_ids: set[str], target_entity_id: int) -> None:
        new_links = [{"description_id": doc_id, "entity_id": target_entity_id} for doc_id in doc_ids]
        stmt = insert(ArchiveDocumentEntity).values(new_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def link_entities_to_document(self, description_id: str, entity_ids: list[int]) -> None:
        """Links multiple entities to a single document (Used in Ingestion / Worker)."""
        if not entity_ids:
            return

        # We use set(entity_ids) to avoid trying to insert the same entity twice in the same document
        new_links = [{"description_id": description_id, "entity_id": e_id} for e_id in set(entity_ids)]
        stmt = insert(ArchiveDocumentEntity).values(new_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def bulk_link_entities(self, links_data: list[dict]) -> None:
        """
        Optimization for Batch Ingestion (Workers).
        Inserts thousands of N:N links in a single transaction.
        Receives: [{"description_id": "doc1", "entity_id": 1}, ...]
        """
        if not links_data:
            return

        # Converts to tuples and then back to dict to remove exact duplicates
        # sent in the same batch, preventing unnecessary locks
        unique_links = [dict(t) for t in {tuple(d.items()) for d in links_data}]

        stmt = insert(ArchiveDocumentEntity).values(unique_links).on_conflict_do_nothing()
        self.db.execute(stmt)

    def create_synonyms(self, synonyms_data: list[dict]) -> None:
        stmt = insert(DomainSynonyms).values(synonyms_data).on_conflict_do_nothing()
        self.db.execute(stmt)

    def delete_entities(self, entity_ids: list[int]) -> int:
        # The associative deletion (ArchiveDocumentEntity) also lives here
        self.db.execute(delete(ArchiveDocumentEntity).where(ArchiveDocumentEntity.entity_id.in_(entity_ids)))

        result = self.db.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id.in_(entity_ids)))
        return cast(CursorResult, result).rowcount

    def update_entity_type(self, entity_id: int, new_type: str) -> None:
        """Updates the category (PER, LOC, ORG) of a canonical entity."""
        # Adjust 'Entity' to the exact name of your SQLAlchemy Model class
        entity = self.db.query(ArchiveEntity).filter(ArchiveEntity.entity_id == entity_id).first()
        if entity:
            entity.entity_type = new_type

    def update_entity_name(self, entity_id: int, new_name: str) -> None:
        entity = self.db.query(ArchiveEntity).filter(ArchiveEntity.entity_id == entity_id).first()
        if entity:
            entity.name = new_name

    def save_entity_stopwords(self, words: list[str]) -> None:
        """Saves the words to the blacklist with the scope exclusive to Entities."""
        for word in words:
            clean_word = word.strip().lower()

            # Checks whether it already exists to avoid a Unique Constraint error
            exists = self.db.query(DomainStopwords).filter_by(word=clean_word, word_scope=StopwordsScope.ENTITY).first()

            if not exists:
                new_stopword = DomainStopwords(word=clean_word, word_scope=StopwordsScope.ENTITY)
                self.db.add(new_stopword)

    def delete_entities_by_names(self, names: list[str]) -> int:
        """Deletes entities from the collection by searching for a list of exact names."""
        clean_names = [n.strip().lower() for n in names]

        deleted_rows = (
            self.db.query(ArchiveEntity)
            .filter(func.lower(ArchiveEntity.name).in_(clean_names))
            .delete(synchronize_session=False)
        )

        return deleted_rows

    # --- Analytical Queries and Maintenance ---

    def get_relevance_count(
        self, entity_type: Literal["ORG", "PER", "LOC"] | None = None, limit: int = 30
    ) -> Sequence[Row]:
        """Fetches the most referenced entities in documents."""
        stmt = select(
            ArchiveEntity.entity_id,
            ArchiveEntity.name,
            ArchiveEntity.entity_type,
            func.count(ArchiveDocumentEntity.description_id).label("total_usage"),
        ).join(ArchiveDocumentEntity, ArchiveEntity.entity_id == ArchiveDocumentEntity.entity_id)

        if entity_type:
            stmt = stmt.where(ArchiveEntity.entity_type == entity_type)

        stmt = stmt.group_by(ArchiveEntity.entity_id).order_by(desc("total_usage")).limit(limit)
        return self.db.execute(stmt).all()

    def purge_orphan_entities(self) -> int:
        """Finds and deletes entities that do not have any linked document."""
        stmt_orphans = (
            select(ArchiveEntity.entity_id)
            .outerjoin(ArchiveDocumentEntity, ArchiveEntity.entity_id == ArchiveDocumentEntity.entity_id)
            .where(ArchiveDocumentEntity.description_id.is_(None))
        )

        orphans = self.db.scalars(stmt_orphans).all()

        if not orphans:
            return 0

        result = self.db.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id.in_(orphans)))
        return cast(CursorResult, result).rowcount
