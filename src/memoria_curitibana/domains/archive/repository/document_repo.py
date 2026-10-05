import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import Float, and_, bindparam, case, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from memoria_curitibana.core.types import Vector
from memoria_curitibana.domains.archive.domain.hierarchy_code import normalize_reference_code
from memoria_curitibana.domains.archive.domain.normalization import normalize_synonym
from memoria_curitibana.domains.archive.domain.search import build_tsquery, tokenize
from memoria_curitibana.domains.archive.exceptions import (
    EntityNotFoundError,
    HierarchyNodeNotFoundError,
    TagNotFoundError,
)
from memoria_curitibana.domains.archive.models import (
    ArchiveDescriptionLevel,
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveDocumentRevision,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveMacroCategory,
    ArchiveReviewStatus,
    ArchiveTag,
    ArchiveTypology,
    DomainSynonyms,
)
from memoria_curitibana.domains.archive.models.document import EMBEDDING_DIMENSIONS
from memoria_curitibana.domains.archive.repository.governance import ai_writable_documents
from memoria_curitibana.domains.archive.repository.text_quality_repo import (
    ExcerptRule,
    TextQualityRepository,
    apply_excerpts_in_python,
)
from memoria_curitibana.domains.archive.schemas.command_schema import (
    DocumentReviewCommand,
    EntityLinkCommand,
    TagLinkCommand,
)
from memoria_curitibana.domains.archive.schemas.document_schema import (
    ArchiveDocumentDTO,
    DocumentAncestorSummary,
    DocumentFacets,
    DocumentMacroCategorySummary,
    DocumentRevisionDTO,
    DocumentSummary,
    DocumentTagSummary,
    FacetCount,
)
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery
from memoria_curitibana.domains.archive.worker_stamp import (
    HIERARCHY_PARENT,
    HIERARCHY_PARENT_PENDING,
    HIERARCHY_PARENT_RESOLVED,
)

# A document that matches only through its tags or entities (not through its own
# text) still has to surface in the page, so a taxonomy hit outranks a document
# with a very weak text match. It stacks once per axis.
TAXONOMY_MATCH_BOOST = 0.2

#: The two columns that describe *where a description sits*. They are special in the transfer:
#: a payload that omits them is saying "the source declared no arrangement", and the ON CONFLICT
#: must then leave the curated tree exactly as it is. ``upsert_archive_document`` turns that into
#: behaviour by dropping an explicit ``None``, since ``None`` cannot mean "set the column to null"
#: for a NOT NULL path anyway.
ARRANGEMENT_COLUMNS = frozenset({"parent_id", "path"})


def _jsonable(value: Any) -> Any:
    """Turns a column value into something JSONB can hold (dates become ISO strings)."""
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db
        # Title-scoped excerpts are read at most once per repository, on the first summary.
        self._title_rules: list[ExcerptRule] | None = None

    def upsert_archive_document(self, doc_data: ArchiveDocumentDTO) -> bool:
        """
        Inserts or updates the fact document in the Archive layer from the Staging data.

        ⚠️ CRITICAL ARCHITECTURE RESTRICTION (EXCLUSIVE USE IN LOAD/MIGRATION):
        This function is designed UNIQUELY for the Staging -> Archive transfer pipeline.
        The UPDATE will only be executed if the incoming 'staging_content_hash'
        is DIFFERENT from the hash currently persisted in Archive (change at the source).

        🚨 IMPORTANT FOR AI PIPELINES (WORKERS):
        DO NOT use this function to save AI enrichments (spaCy, mDeBERTa).
        Workers update their columns surgically and stamp the ``execution_log``
        via ``WorkerStamp``; the ON CONFLICT would otherwise discard the AI data.

        🔒 GOVERNANCE (HUMAN-IN-THE-LOOP):
        If the document has the 'HUMAN_APPROVED' status, PostgreSQL will block
        any attempt at overwriting, shielding the human review from rollbacks.

        Args:
            db (Session): Active SQLAlchemy session.
            doc_data (ArchiveDocumentDTO): Validated object with ISAD(G) metadata.

        Returns:
            bool: True if the record was created or modified; False if the operation was
                ignored due to Hash consistency or protection of human work.
        """
        db_dict = doc_data.model_dump(exclude_unset=True)
        # ``None`` here is not a value, it is an absence: the source declared no parent, so the
        # INSERT takes the column default (a root) and the UPDATE never mentions the column.
        db_dict = {key: value for key, value in db_dict.items() if value is not None or key not in ARRANGEMENT_COLUMNS}

        stmt = insert(ArchiveDocument).values(db_dict)

        # Protects immutable columns or columns that are the exclusive responsibility of Archive.
        protected_columns = [
            "description_id",  # PK (Never changes)
            "created_at",  # Creation date (Never changes)
            "storage_thumbnail_uri",  # Generated by Storage
        ]

        # Only the columns present in the payload are eligible for the UPDATE. Iterating
        # over ``stmt.excluded`` would expose EVERY table column, nulling out fields
        # (ISAD(G) metadata, anomaly flags, ...) that were not part of this transfer.
        update_dict = {key: stmt.excluded[key] for key in db_dict if key not in protected_columns}
        # Only performs the UPDATE if the current status in the database is NOT HUMAN_APPROVED
        stmt = stmt.on_conflict_do_update(
            index_elements=["description_id"],
            set_=update_dict,
            where=(
                ai_writable_documents() & (ArchiveDocument.staging_content_hash != stmt.excluded.staging_content_hash)
            ),
        )
        stmt = stmt.returning(ArchiveDocument.description_id)

        saved_id = self.db.scalar(stmt)
        return saved_id is not None

    def fetch_documents_for_clustering(self, columns_to_extract: list[str] | None = None) -> list[str]:
        """
        Fetches documents and concatenates the requested textual columns
        into a single cohesive string to feed the AI.

        Ordered by ``description_id`` on purpose: without it PostgreSQL is free to return the rows
        in any order, and the clustering suggestion would then depend on the plan rather than on
        the collection.
        """
        columns = columns_to_extract or ["original_title", "admin_bio_history", "provenance", "scope_content"]

        filters = [getattr(ArchiveDocument, col).is_not(None) for col in columns]
        stmt = select(ArchiveDocument).where(or_(*filters)).order_by(ArchiveDocument.description_id)

        docs = self.db.scalars(stmt).all()
        clean_txt = []

        for doc in docs:
            parts = []
            for col in columns:
                val = getattr(doc, col)
                # Ensures it is not null, is a string and is not empty (only spaces)
                if val and isinstance(val, str) and val.strip():
                    # Removes line breaks to avoid confusing the algorithm
                    clean_text = re.sub(r"\s+", " ", val.strip())
                    if clean_text:
                        parts.append(clean_text)

            if parts:
                # Joins the Title with the Description using a period and a space
                clean_txt.append(". ".join(parts) + ".")

        return clean_txt

    # ==========================================
    # READING AND CURATION (HUMAN-IN-THE-LOOP)
    # ==========================================

    @staticmethod
    def _eager_options() -> tuple[Any, ...]:
        """Eager loads tags (with their macro category), entities, the level and the typology, avoiding N+1."""
        return (
            selectinload(ArchiveDocument.tags).selectinload(ArchiveTag.macro_category),
            selectinload(ArchiveDocument.entities),
            # ``DocumentSummary.level`` is derived from this relationship, so without the eager
            # load every read view would issue one extra query per document.
            selectinload(ArchiveDocument.level_ref),
            # Same reason: ``DocumentSummary.typology`` is the name behind the foreign key.
            selectinload(ArchiveDocument.typology_ref),
        )

    def _decorate(
        self, nodes: list[ArchiveDocument]
    ) -> tuple[dict[str, list[DocumentAncestorSummary]], dict[str, int]]:
        """
        Resolves the branch and the child count of a whole page in **two** queries.

        The ancestors come out of the materialised paths, so the set of ids to read is known before
        reading anything; the child counts are one grouped count. Doing it per document would turn
        a page of fifty into a hundred extra round trips, which is the N+1 the tree work is
        supposed to avoid rather than introduce.
        """
        if not nodes:
            return {}, {}

        ancestor_ids: set[str] = set()
        for node in nodes:
            ancestor_ids.update(node.path.split(".")[:-1])

        ancestors_by_id: dict[str, list[DocumentAncestorSummary]] = {}
        if ancestor_ids:
            stmt = (
                select(ArchiveDocument)
                .where(ArchiveDocument.description_id.in_(ancestor_ids))
                .options(selectinload(ArchiveDocument.level_ref))
            )
            chain_nodes = {node.description_id: node for node in self.db.scalars(stmt).all()}
            for node in nodes:
                ancestors_by_id[node.description_id] = [
                    DocumentAncestorSummary(
                        description_id=ancestor.description_id,
                        title=ancestor.final_title or ancestor.original_title,
                        level=ancestor.level,
                    )
                    for ancestor_id in node.path.split(".")[:-1]
                    if (ancestor := chain_nodes.get(ancestor_id)) is not None
                ]

        description_ids = [node.description_id for node in nodes]
        count_rows = self.db.execute(
            select(ArchiveDocument.parent_id, func.count())
            .where(ArchiveDocument.parent_id.in_(description_ids))
            .group_by(ArchiveDocument.parent_id)
        ).all()
        counts = {str(parent_id): int(count) for parent_id, count in count_rows}

        return ancestors_by_id, counts

    def _page_summaries(self, rows: list[tuple[ArchiveDocument, float | None]]) -> list[DocumentSummary]:
        """Builds the read view of a page, decorating it once instead of once per row."""
        ancestors, counts = self._decorate([node for node, _rank in rows])
        return [
            self._to_summary(
                node,
                rank,
                ancestors.get(node.description_id, []),
                counts.get(node.description_id, 0),
            )
            for node, rank in rows
        ]

    def _to_summary(
        self,
        doc: ArchiveDocument,
        rank: float | None = None,
        ancestors: list[DocumentAncestorSummary] | None = None,
        children_count: int = 0,
    ) -> DocumentSummary:
        """
        Builds the read view, the macro-category vote and the suggested title.

        The vote counts how many of the document's tags belong to each category, so a
        document whose tags are mostly "Urbanismo" ranks Urbanismo first. It is derived
        on read from the tags already eagerly loaded, which keeps a tag edit instantly
        visible on every linked document without writing to ``archive_documents``.

        ``rank`` is the relevance score of a free-text search, and stays ``None`` when
        the caller is browsing the collection instead of searching it.
        """
        summary = DocumentSummary.model_validate(doc)
        summary.rank = rank
        summary.suggested_final_title = self._suggest_title(doc)
        summary.ancestors = ancestors or []
        summary.children_count = children_count
        # The subject decision travels with each tag: the tab has to show *why* a document is
        # filed where it is, and asking a second route per tag would be an N+1 on the front-end.
        summary.tags = [
            DocumentTagSummary(
                tag_id=tag.tag_id,
                name=tag.name,
                macro_category_id=tag.macro_category_id,
                macro_category_name=tag.macro_category.name if tag.macro_category else None,
                ai_confidence_score=tag.ai_confidence_score,
            )
            for tag in sorted(doc.tags, key=lambda tag: tag.name)
        ]

        votes: dict[int, DocumentMacroCategorySummary] = {}
        for tag in doc.tags:
            category = tag.macro_category
            if category is None:
                continue

            current = votes.get(category.category_id)
            if current is None:
                votes[category.category_id] = DocumentMacroCategorySummary(
                    category_id=category.category_id, name=category.name, tag_count=1
                )
            else:
                current.tag_count += 1

        summary.macro_categories = sorted(votes.values(), key=lambda vote: (-vote.tag_count, vote.name))
        return summary

    def _suggest_title(self, doc: ArchiveDocument) -> str | None:
        """
        Title without the fixed part the curation approved, or ``None`` when there is none.

        Derived on read: the machine proposes and the archivist writes ``final_title``.
        Once the human wrote it there is nothing left to propose, so the suggestion
        disappears instead of nagging.
        """
        if doc.final_title or not (doc.original_title or "").strip():
            return None

        if self._title_rules is None:
            self._title_rules = TextQualityRepository(self.db).get_active_rules("TITLE")
        if not self._title_rules:
            return None

        suggested = apply_excerpts_in_python(doc.original_title, self._title_rules)
        return suggested or None

    @staticmethod
    def _facet_filters(
        query: DocumentSearchQuery,
        ancestor_path: str | None = None,
        exclude: frozenset[str] = frozenset(),
    ) -> list[Any]:
        """
        Builds the facet predicates shared by the count, the page and the facet counts.

        ``ancestor_path`` arrives already resolved: turning ``ancestor_id`` into a path is a lookup,
        and doing it here would mean a query per facet evaluation.

        ``exclude`` names the dimension whose own filter must be left out. Counting a facet under
        its own selection is what makes a sidebar a dead end: with "Dossiê" applied, every other
        rung would report zero and the user could not widen the search back.
        """
        filters: list[Any] = []

        # The diffusion gate comes first and is never excluded: it is not a filter the user chose,
        # it is the institution's decision about what exists in public. No facet may lift it.
        if query.published_only:
            filters.append(ArchiveDocument.is_published.is_(True))
        if query.typology_id is not None and "typology" not in exclude:
            filters.append(ArchiveDocument.typology_id == query.typology_id)
        if query.level_id is not None and "level" not in exclude:
            filters.append(ArchiveDocument.level_id == query.level_id)
        if ancestor_path is not None:
            # The whole reason the path is materialised: one indexed prefix match answers
            # "everything inside this fonds/série", at any depth, without a recursive walk.
            filters.append(
                or_(
                    ArchiveDocument.path == ancestor_path,
                    ArchiveDocument.path.like(f"{ancestor_path}.%"),
                )
            )
        if query.date_from is not None:
            filters.append(ArchiveDocument.document_date >= query.date_from)
        if query.date_to is not None:
            filters.append(ArchiveDocument.document_date <= query.date_to)
        if query.status is not None:
            filters.append(ArchiveDocument.review_status == query.status)
        if query.is_anomaly is not None:
            filters.append(ArchiveDocument.is_anomaly.is_(query.is_anomaly))
        if query.macro_category_id is not None and "macro_category" not in exclude:
            filters.append(
                exists(
                    select(1)
                    .select_from(ArchiveDocumentTag)
                    .join(ArchiveTag, ArchiveDocumentTag.tag_id == ArchiveTag.tag_id)
                    .where(
                        ArchiveDocumentTag.description_id == ArchiveDocument.description_id,
                        ArchiveTag.macro_category_id == query.macro_category_id,
                    )
                )
            )
        if query.entity_type is not None and "entity_type" not in exclude:
            filters.append(
                exists(
                    select(1)
                    .select_from(ArchiveDocumentEntity)
                    .join(ArchiveEntity, ArchiveDocumentEntity.entity_id == ArchiveEntity.entity_id)
                    .where(
                        ArchiveDocumentEntity.description_id == ArchiveDocument.description_id,
                        ArchiveEntity.entity_type == query.entity_type,
                    )
                )
            )

        return filters

    # ==========================================
    # FACETS OF THE SEARCH SIDEBAR
    # ==========================================
    def _facets(
        self,
        query: DocumentSearchQuery,
        ancestor_path: str | None,
        term_clause: Any | None = None,
        extra_clauses: tuple[Any, ...] = (),
    ) -> DocumentFacets:
        """
        Counts each facet dimension over the result set, minus the dimension's own filter.

        ``term_clause`` is the *same* clause the page query used, so the sidebar can never disagree
        with the list it describes; ``extra_clauses`` carries the semantic restriction (documents
        that have an embedding), which is part of the result set rather than a user filter.
        """

        def clauses_for(dimension: str) -> list[Any]:
            clauses = self._facet_filters(query, ancestor_path, frozenset({dimension}))
            if term_clause is not None:
                clauses.append(term_clause)
            clauses.extend(extra_clauses)
            return clauses

        return DocumentFacets(
            typology=self._typology_facet(clauses_for("typology")),
            macro_category=self._macro_category_facet(clauses_for("macro_category")),
            entity_type=self._entity_type_facet(clauses_for("entity_type")),
            level=self._level_facet(clauses_for("level")),
        )

    def _typology_facet(self, clauses: list[Any]) -> list[FacetCount]:
        stmt = (
            select(ArchiveDocument.typology_id, ArchiveTypology.name, func.count())
            .join(ArchiveTypology, ArchiveDocument.typology_id == ArchiveTypology.typology_id)
            .where(*clauses)
            .group_by(ArchiveDocument.typology_id, ArchiveTypology.name)
        )
        rows = sorted(self.db.execute(stmt).all(), key=lambda row: (-int(row[2]), str(row[1])))
        return [
            FacetCount(key=str(typology_id), label=str(name), count=int(count)) for typology_id, name, count in rows
        ]

    def _macro_category_facet(self, clauses: list[Any]) -> list[FacetCount]:
        # ``DISTINCT description_id`` because the joins fan a document out over its matching tags:
        # counting rows instead of documents would inflate every category by the number of tags.
        stmt = (
            select(
                ArchiveMacroCategory.category_id,
                ArchiveMacroCategory.name,
                func.count(func.distinct(ArchiveDocument.description_id)),
            )
            .select_from(ArchiveDocument)
            .join(ArchiveDocumentTag, ArchiveDocumentTag.description_id == ArchiveDocument.description_id)
            .join(ArchiveTag, ArchiveDocumentTag.tag_id == ArchiveTag.tag_id)
            .join(ArchiveMacroCategory, ArchiveTag.macro_category_id == ArchiveMacroCategory.category_id)
            .where(*clauses)
            .group_by(ArchiveMacroCategory.category_id, ArchiveMacroCategory.name)
        )
        rows = sorted(self.db.execute(stmt).all(), key=lambda row: (-int(row[2]), str(row[1])))
        return [
            FacetCount(key=str(category_id), label=str(name), count=int(count)) for category_id, name, count in rows
        ]

    def _entity_type_facet(self, clauses: list[Any]) -> list[FacetCount]:
        stmt = (
            select(ArchiveEntity.entity_type, func.count(func.distinct(ArchiveDocument.description_id)))
            .select_from(ArchiveDocument)
            .join(ArchiveDocumentEntity, ArchiveDocumentEntity.description_id == ArchiveDocument.description_id)
            .join(ArchiveEntity, ArchiveDocumentEntity.entity_id == ArchiveEntity.entity_id)
            .where(*clauses)
            .group_by(ArchiveEntity.entity_type)
        )
        rows = sorted(self.db.execute(stmt).all(), key=lambda row: (-int(row[1]), str(row[0])))
        return [
            FacetCount(key=str(entity_type), label=str(entity_type), count=int(count)) for entity_type, count in rows
        ]

    def _level_facet(self, clauses: list[Any]) -> list[FacetCount]:
        # Ordered by the catalogue's ordinal, not by count: the rungs are a ladder, and a list
        # sorted by popularity reads as if the arrangement had no order.
        stmt = (
            select(
                ArchiveDocument.level_id, ArchiveDescriptionLevel.name, ArchiveDescriptionLevel.ordinal, func.count()
            )
            .join(ArchiveDescriptionLevel, ArchiveDocument.level_id == ArchiveDescriptionLevel.level_id)
            .where(*clauses)
            .group_by(ArchiveDocument.level_id, ArchiveDescriptionLevel.name, ArchiveDescriptionLevel.ordinal)
        )
        rows = sorted(self.db.execute(stmt).all(), key=lambda row: int(row[2]))
        return [
            FacetCount(key=str(level_id), label=str(name), count=int(count)) for level_id, name, _ordinal, count in rows
        ]

    @staticmethod
    def _taxonomy_match(
        link_model: Any,
        name_model: Any,
        join_on: Any,
        name_column: Any,
        tokens: list[str],
        canonical_synonym: Any | None = None,
    ) -> Any:
        """
        ``EXISTS`` on a link table whose related name contains every search token.

        ``EXISTS`` instead of a join keeps a document with several matching tags from
        being duplicated in the page or double-counted in ``total``. The ``ILIKE`` on
        the names is what the existing ``gin_trgm_ops`` indexes accelerate.

        ``canonical_synonym`` adds the direct path from an absorbed spelling to the
        canonical it was merged into (see ``_merged_spelling_match``), as an *alternative*
        to the token condition — the token semantics (all tokens required) stay untouched.
        """
        token_condition = and_(*(name_column.ilike(f"%{token}%") for token in tokens))
        condition = token_condition if canonical_synonym is None else or_(token_condition, canonical_synonym)

        return exists(
            select(1)
            .select_from(link_model)
            .join(name_model, join_on)
            .where(link_model.description_id == ArchiveDocument.description_id, condition)
        )

    @staticmethod
    def _merged_spelling_match(id_column: Any, canonical_column: Any, categories: list[str], term: str) -> Any:
        """
        Matches the canonical row a searched spelling was merged into.

        The dedup deletes the absorbed spelling, so without this the user who types it loses
        the documents that were reachable only through it. Measured on the real collection
        after canonicalising 40 plural pairs: ``lojas`` lost 42 of its 54 documents and
        ``homens`` lost 30 of 35 — the full-text stemmer covers the ones whose *text* carries
        the word, not the ones that only had the tag. The synonym the merge wrote is the
        mapping that closes the gap.
        """
        normalized = normalize_synonym(term)
        if not normalized:
            return None

        targets = select(canonical_column).where(
            DomainSynonyms.category.in_(categories),
            DomainSynonyms.synonym_name == normalized,
            canonical_column.is_not(None),
        )
        return id_column.in_(targets)

    @staticmethod
    def _contains_condition(tokens: list[str]) -> Any:
        """
        Legacy substring match over the document text.

        Full-text search is lexeme/prefix based and misses a term in the middle of a
        word ("rbanis" does not match "urbanismo"). When the ranked query finds
        nothing, this condition replaces it so partial words keep working.
        """
        columns = (ArchiveDocument.final_title, ArchiveDocument.original_title, ArchiveDocument.scope_content)
        return or_(*(and_(*(column.ilike(f"%{token}%") for token in tokens)) for column in columns))

    def _count(self, stmt: Any) -> int:
        return self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    def _browse_page(self, stmt: Any, query: DocumentSearchQuery) -> list[DocumentSummary]:
        """Page of documents with no relevance: most recently updated first."""
        page_stmt = (
            stmt.options(*self._eager_options())
            .order_by(ArchiveDocument.updated_at.desc(), ArchiveDocument.description_id)
            .limit(query.limit)
            .offset(query.offset)
        )
        return self._page_summaries([(doc, None) for doc in self.db.scalars(page_stmt).all()])

    def _semantic_search(
        self, base_stmt: Any, query: DocumentSearchQuery, query_embedding: list[float]
    ) -> tuple[list[DocumentSummary], int, DocumentFacets]:
        """
        Ranks the embedded documents by cosine similarity to the query vector.

        Only documents that already have an embedding are candidates, so the worker has
        to have run before semantic search returns anything. ``rank`` is the cosine
        similarity (1 = same direction), which is friendlier to read than the raw
        distance the index is ordered by.
        """
        query_vector = bindparam("query_embedding", value=query_embedding, type_=Vector(EMBEDDING_DIMENSIONS))
        # ``return_type`` matters: without it SQLAlchemy infers the operator result from
        # the left operand (the vector column), and then ``1 - distance`` would try to
        # bind the literal 1 as a vector.
        distance = ArchiveDocument.embedding.op("<=>", return_type=Float)(query_vector)
        rank = (1 - distance).label("rank")

        has_embedding = ArchiveDocument.embedding.is_not(None)
        stmt = base_stmt.where(has_embedding).add_columns(rank)
        total = self._count(stmt)

        page_stmt = (
            stmt.options(*self._eager_options())
            .order_by(distance.asc(), ArchiveDocument.updated_at.desc(), ArchiveDocument.description_id)
            .limit(query.limit)
            .offset(query.offset)
        )
        rows = self.db.execute(page_stmt).all()
        items = self._page_summaries([(doc, float(relevance)) for doc, relevance in rows])
        facets = self._facets(
            query,
            self._ancestor_path(query.ancestor_id),
            extra_clauses=(has_embedding,),
        )
        return items, total, facets

    def search(
        self, query: DocumentSearchQuery, query_embedding: list[float] | None = None
    ) -> tuple[list[DocumentSummary], int, DocumentFacets]:
        """
        Searches the collection with native full-text ranking and facets.

        The term is matched against the generated ``search_vector`` (Portuguese
        dictionary, accent-insensitive, titles weighted above the body) **and** against
        the tag/entity names. Facets are applied to the page and to the total.

        The substring fallback runs only when the ranked query finds nothing at all, so
        a normal search never scans the text columns. It is there to keep a mid-word
        fragment (which FTS cannot see) from returning an empty page when no tag or
        entity matches either.

        When ``query.mode`` is ``semantic`` and a ``query_embedding`` is provided, the
        full-text clause is replaced by the cosine-distance ranking; the facets still
        apply.

        The facet counts are computed from **the same clause the page came from** (whichever
        branch resolved it, fallback included), so the sidebar can never disagree with the list
        it describes.
        """
        ancestor_path = self._ancestor_path(query.ancestor_id)
        base_stmt = select(ArchiveDocument).where(*self._facet_filters(query, ancestor_path))

        if query.mode == "semantic" and query_embedding is not None:
            return self._semantic_search(base_stmt, query, query_embedding)

        tokens = tokenize(query.term) if query.term else []
        tsquery = build_tsquery(tokens)

        if tsquery:
            ts_query = func.to_tsquery("portuguese", func.immutable_unaccent(tsquery))
            merged_term = " ".join(tokens)
            tag_match = self._taxonomy_match(
                ArchiveDocumentTag,
                ArchiveTag,
                ArchiveDocumentTag.tag_id == ArchiveTag.tag_id,
                ArchiveTag.name,
                tokens,
                canonical_synonym=self._merged_spelling_match(
                    ArchiveTag.tag_id, DomainSynonyms.canonical_tag_id, ["TAG"], merged_term
                ),
            )
            entity_match = self._taxonomy_match(
                ArchiveDocumentEntity,
                ArchiveEntity,
                ArchiveDocumentEntity.entity_id == ArchiveEntity.entity_id,
                ArchiveEntity.name,
                tokens,
                canonical_synonym=self._merged_spelling_match(
                    ArchiveEntity.entity_id,
                    DomainSynonyms.canonical_entity_id,
                    ["ORG", "PER", "LOC"],
                    merged_term,
                ),
            )
            rank = (
                func.ts_rank(ArchiveDocument.search_vector, ts_query)
                + case((tag_match, TAXONOMY_MATCH_BOOST), else_=0.0)
                + case((entity_match, TAXONOMY_MATCH_BOOST), else_=0.0)
            ).label("rank")
            term_clause = or_(ArchiveDocument.search_vector.op("@@")(ts_query), tag_match, entity_match)
            # The relevance has to be selected, not only ordered by, so the read view
            # can expose it and the caller can explain the ordering.
            ranked_stmt = base_stmt.where(term_clause).add_columns(rank)

            total = self._count(ranked_stmt)
            if total:
                page_stmt = (
                    ranked_stmt.options(*self._eager_options())
                    .order_by(rank.desc(), ArchiveDocument.updated_at.desc(), ArchiveDocument.description_id)
                    .limit(query.limit)
                    .offset(query.offset)
                )
                rows = self.db.execute(page_stmt).all()
                items = self._page_summaries([(doc, float(relevance)) for doc, relevance in rows])
                return items, total, self._facets(query, ancestor_path, term_clause=term_clause)

            if tokens:
                fallback_clause = self._contains_condition(tokens)
                fallback_stmt = base_stmt.where(fallback_clause)
                total = self._count(fallback_stmt)
                if total:
                    items = self._browse_page(fallback_stmt, query)
                    return items, total, self._facets(query, ancestor_path, term_clause=fallback_clause)
            return [], 0, DocumentFacets()

        return (
            self._browse_page(base_stmt, query),
            self._count(base_stmt),
            self._facets(query, ancestor_path),
        )

    def _ancestor_path(self, ancestor_id: str | None) -> str | None:
        """
        Turns the branch the caller asked for into the path the filter matches on.

        A branch that does not exist is a **404**, not an empty page: returning nothing for a typo
        would look like "this fonds holds no description", which is a different and wrong statement.
        """
        if not ancestor_id:
            return None
        path = self.db.scalar(select(ArchiveDocument.path).where(ArchiveDocument.description_id == ancestor_id))
        if path is None:
            raise HierarchyNodeNotFoundError(f"Descrição '{ancestor_id}' não encontrada no acervo.")
        return path

    def get_by_id(self, description_id: str) -> DocumentSummary | None:
        """Loads a document with tags and entities for reading/editing."""
        stmt = (
            select(ArchiveDocument)
            .where(ArchiveDocument.description_id == description_id)
            .options(*self._eager_options())
        )
        doc = self.db.scalars(stmt).first()
        return self._page_summaries([(doc, None)])[0] if doc else None

    def update_review(self, command: DocumentReviewCommand) -> DocumentSummary | None:
        """
        Applies the archivist's edits and shields the document against the AI.

        Any manually edited document becomes `HUMAN_APPROVED`, which
        prevents overwriting by the migration/AI pipeline.

        Every field that actually changes is written to ``archive_document_revisions`` with
        its before/after and the author, so a correction can be explained later. Fields the
        command did not send are left untouched, and a field sent with the same value is not
        recorded as a change.
        """
        doc = self._get_orm_by_id(command.description_id)
        if doc is None:
            return None

        changes = command.model_dump(exclude_unset=True, exclude={"description_id", "changed_by", "review_note"})
        diff: dict[str, dict[str, Any]] = {}

        for field, value in changes.items():
            previous = getattr(doc, field)
            if previous == value:
                continue
            diff[field] = {"old": _jsonable(previous), "new": _jsonable(value)}
            setattr(doc, field, value)

        if diff:
            self.db.add(
                ArchiveDocumentRevision(
                    description_id=doc.description_id,
                    changed_by=command.changed_by,
                    changes=diff,
                    note=command.review_note,
                )
            )

        doc.review_status = ArchiveReviewStatus.HUMAN_APPROVED
        self.db.flush()
        return self._page_summaries([(doc, None)])[0]

    def list_revisions(self, description_id: str) -> list[DocumentRevisionDTO]:
        """Audit trail of one document, newest first."""
        stmt = (
            select(ArchiveDocumentRevision)
            .where(ArchiveDocumentRevision.description_id == description_id)
            .order_by(ArchiveDocumentRevision.created_at.desc(), ArchiveDocumentRevision.revision_id.desc())
        )
        return [DocumentRevisionDTO.model_validate(row) for row in self.db.scalars(stmt).all()]

    # =========================================================================
    # Local curation of one document's subjects (Fase 4)
    # =========================================================================
    #
    # The taxonomy routes merge *terms* globally; these four actions edit what one description
    # carries. Both are curation, but only this one can be expressed as "this document is about
    # this too", which is the decision an archivist actually makes while reading a record.
    def _curate_relation(
        self,
        doc: ArchiveDocument,
        field: str,
        names_before: list[str],
        names_after: list[str],
        changed_by: str | None,
        note: str | None,
    ) -> None:
        """
        Records the before/after of a subject edit and shields the document from the AI.

        Same rule as the field edit: the human decision wins and is explained. The whole list of
        names is stored on each side rather than a diff of ids, because the names are what the
        archivist decided and an id would not survive a rename.
        """
        if names_before != names_after:
            self.db.add(
                ArchiveDocumentRevision(
                    description_id=doc.description_id,
                    changed_by=changed_by,
                    changes={field: {"old": names_before, "new": names_after}},
                    note=note,
                )
            )

        # Deliberate, and the same choice ``update_review`` makes: a human touching the subjects of
        # a record takes responsibility for it, so the AI stops rewriting it. The UI says so.
        doc.review_status = ArchiveReviewStatus.HUMAN_APPROVED
        self.db.flush()

    @staticmethod
    def _related_names(collection: list[Any]) -> list[str]:
        return sorted(str(item.name) for item in collection)

    def link_tag(
        self, command: TagLinkCommand, changed_by: str | None = None, note: str | None = None
    ) -> DocumentSummary | None:
        """Attaches one tag to one document as a human decision, with an audit entry."""
        doc = self._get_orm_by_id(command.description_id)
        if doc is None:
            return None

        tag = self.db.get(ArchiveTag, command.tag_id)
        if tag is None:
            raise TagNotFoundError(f"Tag '{command.tag_id}' não encontrada na taxonomia.")

        before = self._related_names(doc.tags)
        if command.tag_id not in {linked.tag_id for linked in doc.tags}:
            doc.tags.append(tag)
        self._curate_relation(doc, "tags", before, self._related_names(doc.tags), changed_by, note)
        return self._page_summaries([(doc, None)])[0]

    def unlink_tag(
        self, command: TagLinkCommand, changed_by: str | None = None, note: str | None = None
    ) -> DocumentSummary | None:
        """Detaches one tag from one document as a human decision, with an audit entry."""
        doc = self._get_orm_by_id(command.description_id)
        if doc is None:
            return None

        linked = next((tag for tag in doc.tags if tag.tag_id == command.tag_id), None)
        if linked is None:
            raise TagNotFoundError(f"A descrição '{command.description_id}' não tem a tag '{command.tag_id}'.")

        before = self._related_names(doc.tags)
        doc.tags.remove(linked)
        self._curate_relation(doc, "tags", before, self._related_names(doc.tags), changed_by, note)
        return self._page_summaries([(doc, None)])[0]

    def link_entity(
        self, command: EntityLinkCommand, changed_by: str | None = None, note: str | None = None
    ) -> DocumentSummary | None:
        """Attaches one named entity to one document as a human decision, with an audit entry."""
        doc = self._get_orm_by_id(command.description_id)
        if doc is None:
            return None

        entity = self.db.get(ArchiveEntity, command.entity_id)
        if entity is None:
            raise EntityNotFoundError(f"Entidade '{command.entity_id}' não encontrada.")

        before = self._related_names(doc.entities)
        if command.entity_id not in {linked.entity_id for linked in doc.entities}:
            doc.entities.append(entity)
        self._curate_relation(doc, "entities", before, self._related_names(doc.entities), changed_by, note)
        return self._page_summaries([(doc, None)])[0]

    def unlink_entity(
        self, command: EntityLinkCommand, changed_by: str | None = None, note: str | None = None
    ) -> DocumentSummary | None:
        """Detaches one named entity from one document as a human decision, with an audit entry."""
        doc = self._get_orm_by_id(command.description_id)
        if doc is None:
            return None

        linked = next((entity for entity in doc.entities if entity.entity_id == command.entity_id), None)
        if linked is None:
            raise EntityNotFoundError(
                f"A descrição '{command.description_id}' não tem a entidade '{command.entity_id}'."
            )

        before = self._related_names(doc.entities)
        doc.entities.remove(linked)
        self._curate_relation(doc, "entities", before, self._related_names(doc.entities), changed_by, note)
        return self._page_summaries([(doc, None)])[0]

    def _get_orm_by_id(self, description_id: str) -> ArchiveDocument | None:
        """Internal ORM lookup used by write flows that need the managed entity."""
        stmt = (
            select(ArchiveDocument)
            .where(ArchiveDocument.description_id == description_id)
            .options(*self._eager_options())
        )
        return self.db.scalars(stmt).first()

    # =========================================================================
    # H6 — Resolving the parent the source declares
    # =========================================================================
    def find_by_reference_code(self, reference_code: str) -> ArchiveDocument | None:
        """
        The description whose reference code is exactly this one, folded for case and spacing.

        The fold is what makes the match survive the origin's inconsistencies, and it is the reason
        the comparison cannot use a plain index: ``upper(btrim(...))`` is a functional one. The
        lookup is called once per *distinct* declared parent per run (the worker caches it), so the
        scan is bounded by the vocabulary of the origin rather than by the size of the collection.
        """
        normalized = normalize_reference_code(reference_code)
        if not normalized:
            return None
        stmt = select(ArchiveDocument).where(func.upper(func.btrim(ArchiveDocument.reference_code)) == normalized)
        return self.db.scalars(stmt).first()

    def list_pending_hierarchy_parents(self) -> list[tuple[str, str]]:
        """
        Descriptions still waiting for the parent their origin declared.

        The value convention lives in ``worker_stamp.HIERARCHY_PARENT``; the filter is on the same
        JSONB the idempotency queries already read, so it is a GIN-indexed predicate rather than a
        second ledger.
        """
        stamp_key = HIERARCHY_PARENT.key
        pending_value = ArchiveDocument.execution_log[stamp_key].astext
        stmt = select(ArchiveDocument.description_id, pending_value).where(
            pending_value.like(f"{HIERARCHY_PARENT_PENDING}%")
        )
        return [
            (str(description_id), str(value)[len(HIERARCHY_PARENT_PENDING) :])
            for description_id, value in self.db.execute(stmt).all()
        ]

    def resolve_hierarchy_parent(self, description_id: str, parent_id: str, parent_path: str) -> None:
        """
        Links a description that was waiting for its declared parent, and stamps it as done.

        Only ``parent_id`` and ``path`` are written: this is the arrangement the source declared,
        never the descriptive content, and it must not touch anything a worker produced.
        """
        node = self.db.get(ArchiveDocument, description_id)
        if node is None:
            return
        node.parent_id = parent_id
        node.path = f"{parent_path}.{description_id}"
        node.execution_log = HIERARCHY_PARENT.mark_value(node.execution_log, f"{HIERARCHY_PARENT_RESOLVED}{parent_id}")
        flag_modified(node, "execution_log")
