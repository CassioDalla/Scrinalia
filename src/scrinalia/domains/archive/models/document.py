from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scrinalia.core.base import Base
from scrinalia.core.language import get_language
from scrinalia.core.types import Vector

from .enums import ArchiveReviewStatus

# Type-checker only, and load-bearing: the ``Mapped[...]`` strings below need these names. Keeping
# them inside the guard is what makes CodeQL's ``py/unsafe-cyclic-import`` finding a false positive
# (dismissed); ``testing/unit/quality/test_model_import_cycles.py`` fails if the cycle becomes real.
if TYPE_CHECKING:
    from .associations import ArchiveDocumentEntity
    from .hierarchy import ArchiveDescriptionLevel
    from .taxonomy import ArchiveTag, ArchiveTypology


# Dimension of the embedding model used by the ``multilingual_minilm`` preset
# (``paraphrase-multilingual-MiniLM-L12-v2``). The vector column and the engine preset
# must agree; a unit test guards the pair so changing one without the other fails.
EMBEDDING_DIMENSIONS = 384


# Lexical search vector, computed by PostgreSQL itself.
#
# ``setweight`` gives the titles weight ``A`` and the descriptive body weight ``B``,
# so ``ts_rank`` ranks a title hit above a body hit with no extra plumbing.
# ``immutable_unaccent`` (created by the migration, and by ``testing/conftest.py``)
# makes the search accent-insensitive: without it ``gaucho`` does not find ``Gaúcho``.
# The expression must stay byte-identical to the migration that creates the column;
# Alembic only warns crudely when a computed expression changes.
#
# The dictionary is the language's. Wiring it to the profile means ``ACERVO_LANGUAGE`` cannot be
# changed by an environment variable alone: the column is stored, so a new language needs a
# migration that rebuilds it — and ``alembic check`` reports exactly that drift instead of
# letting the model and the stored expression disagree in silence. The migration keeps its own
# literal on purpose (a migration must keep describing the state it produced).
_FTS_DICTIONARY = get_language().fts_dictionary

DOCUMENT_SEARCH_VECTOR_SQL = (
    f"setweight(to_tsvector('{_FTS_DICTIONARY}', public.immutable_unaccent("
    "coalesce(final_title, '') || ' ' || coalesce(original_title, ''))), 'A')"
    " || "
    f"setweight(to_tsvector('{_FTS_DICTIONARY}', public.immutable_unaccent("
    "coalesce(scope_content, '') || ' ' || coalesce(admin_bio_history, '') || ' ' || coalesce(provenance, ''))), 'B')"
)


def _default_document_path(context: Any) -> str:
    """
    Materialised path of a node that arrives without one.

    A root's path is its own id, so an insert that declares no parent is a root by definition.
    The value is a *default*, not a rule: the transfer and the ``move`` use case pass the path
    explicitly as soon as there is a parent to hang from. Having it here is what keeps every
    existing ``ArchiveDocument(...)`` construction truthful instead of forcing each caller to
    know the base case of the invariant.
    """
    parameters = context.get_current_parameters()
    return parameters.get("path") or parameters["description_id"]


class ArchiveDocument(Base):
    """
    The final, cleaned and enriched document.

    This is the central database served to end users,
    fed by multiple asynchronous Artificial Intelligence workers.
    """

    __tablename__ = "archive_documents"

    description_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # --- Lineage and Origin ---
    #: The ingestion origin whose record produced this description (``pmc``, ``manual``, ...). It is
    #: provenance, not identity: ``description_id`` stays the archival key, and an adapter that can
    #: collide namespaces its own ids. Nullable only for rows written before plural ingestion.
    origin_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: The date as the source spelled it (``Década de 1980``, ``1951-1953``). The parsed column is
    #: lossy by design — an approximate expression becomes a real date at the precision the source
    #: has — so the spelling is kept to be shown. ``None`` when the source sent none.
    date_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    staging_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The URL of the page the record was read from, when the origin had one. It is the record's
    #: source, not the digital object (that is #198): the dossier shows it as "Fonte".
    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_thumbnail_uri: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Archival Metadata (ISAD-G) ---
    reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ``level`` is no longer a text column: it is the name of the catalogue rung, read through
    # ``level_ref`` (see the property below). The free text of 3,608 descriptions was migrated
    # into ``level_id`` by ``b2c3d4e5f6a7`` and the column dropped by ``c3d4e5f6a7b8``.
    #: ISAD(G) 3.1.5, extent and medium of the unit of description.
    dimension_support: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISAD(G) 3.2, the context of creation.
    producers: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_bio_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_archival_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISAD(G) 3.3, content and structure.
    scope_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.3.2, appraisal, destruction and scheduling.
    appraisal_destruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.3.3, accruals.
    accruals: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.3.4, the system of arrangement as text. The *position* is ``parent_id``/``path``;
    #: this is the description of how the record is arranged.
    arrangement: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISAD(G) 3.4, conditions of access and use.
    language_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.4.2, conditions governing reproduction.
    reproduction_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.4.4, physical characteristics and technical requirements.
    physical_characteristics: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.4.5, finding aids.
    finding_aids: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISAD(G) 3.5, allied materials.
    #: ISAD(G) 3.5.1, existence and location of the originals.
    originals_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.5.2, existence and location of copies.
    copies_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.5.3, related units of description.
    related_units: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.5.4, publication note.
    publication_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISAD(G) 3.6, notes. ``conservation_notes`` is not a 3.6.1 sub-field of the norm; it is the
    # institution's own note about the physical state of the record, and the source declares it
    # under its own label, so it is kept apart from the general note instead of merged into it.
    conservation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    general_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISAD(G) 3.7, description control.
    archivist_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.7.2, rules or conventions the description follows.
    rules_conventions: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISAD(G) 3.7.3, date(s) of the description as the source declared them. It is not the
    #: record's own date and it is not the review ledger's timestamp; the archive keeps it because
    #: the source states it, and the dossier shows it beside the record's history.
    description_dates: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISAD(G) 4.1, "Conditions governing access". It was captured by the staging parser and then
    # dropped by the transfer, which meant the archive could not state whether a description is
    # restricted — a defect that only became visible when a diffusion surface was specified.
    access_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Hierarchy of the arrangement (Fase 2.5) ---
    # Self-reference because a fund is an archival description like any other: it has a title,
    # dates and scope, and giving it its own table would duplicate the whole ISAD(G) schema.
    #
    # ``RESTRICT`` and not ``SET NULL``: every descendant's materialised ``path`` carries its
    # ancestors' ids, so a silent ``SET NULL`` would leave a whole subtree pointing at a prefix
    # that no longer exists. A node with children is not deletable in passing.
    #: The parent the origin declared, by reference code. Kept beside ``parent_id`` because the
    #: link may not exist yet: the transfer marks the child pending and the code was, until this
    #: column, stored only inside the ``hierarchy_parent_v1`` stamp value.
    parent_reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(50),
        ForeignKey("archive_documents.description_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    level_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("archive_description_levels.level_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Materialised path of ids ("2368.2732.51931"), maintained by the service, never by the AI.
    # It answers "every descendant of X" with one indexed ``LIKE 'x.%'``, which is the query
    # the tree navigation makes constantly; a ``WITH RECURSIVE`` per node would not hold a
    # 100k-description collection. The index is declared ``text_pattern_ops`` in the table args
    # below because the database collation is not C and a plain btree does not serve ``LIKE``.
    path: Mapped[str] = mapped_column(Text, nullable=False, default=_default_document_path)

    # --- NLP/AI Enrichment ---
    final_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generated by PostgreSQL from the text columns above: it is never written by
    # workers, so it cannot go stale after a human review either. See
    # ``DOCUMENT_SEARCH_VECTOR_SQL`` for the expression and the GIN index below.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(DOCUMENT_SEARCH_VECTOR_SQL, persisted=True),
        nullable=True,
    )

    # Example: {"ner_spacy_v1": "DONE", "mdeberta_tags": "PENDING"}
    execution_log: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Semantic search vector, produced by the ``embedding`` worker from the document
    # text. Unlike ``search_vector`` PostgreSQL cannot generate it, so it is the one
    # AI-produced column that is refreshed even on a HUMAN_APPROVED document: it is a
    # derived index of the text, not archival content. The worker keys it on a hash of
    # the embedded text, so a human edit refreshes it without an AI rewrite.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)

    typology_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_typologies.typology_id", ondelete="SET NULL"), nullable=True, index=True
    )

    # --- Audit (Human-in-the-Loop) ---
    # ``create_type=True`` here is the single owner of the native enum type; the
    # other table that uses ArchiveReviewStatus passes ``create_type=False`` so a
    # ``metadata.create_all`` creates the type exactly once.
    review_status: Mapped[ArchiveReviewStatus] = mapped_column(
        Enum(ArchiveReviewStatus, name="archive_review_status_enum", create_type=True),
        default=ArchiveReviewStatus.PENDING_AI,
        nullable=False,
        index=True,
    )
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    anomaly_reasons: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # --- Relationships---
    # The association object and not the bare ``ArchiveEntity``: the link itself carries the origin
    # (who wrote it), so a relationship over the secondary table would hide the one column the
    # screen has to show.
    entity_links: Mapped[list["ArchiveDocumentEntity"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )
    tags: Mapped[list["ArchiveTag"]] = relationship(secondary="archive_document_tags", back_populates="descriptions")
    # ``typology_ref`` and not ``typology``: the plain name is the *read contract* (the name a
    # client shows), exposed by the property below, exactly as ``level``/``level_ref`` does. Without
    # the split, ``DocumentSummary.model_validate(doc)`` would try to validate the ORM object as the
    # string the read view declares.
    typology_ref: Mapped["ArchiveTypology"] = relationship(back_populates="documents")

    # ``remote_side`` marks the "one" end of the self-referential join; without it SQLAlchemy
    # cannot tell which column points at which on the same table.
    parent: Mapped["ArchiveDocument | None"] = relationship(remote_side=[description_id], back_populates="children")
    children: Mapped[list["ArchiveDocument"]] = relationship(back_populates="parent")
    level_ref: Mapped["ArchiveDescriptionLevel | None"] = relationship(back_populates="descriptions")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def level(self) -> str | None:
        """
        Name of the description level, kept as the read contract after the text column left.

        The archive used to store ``level`` as free text and the API has always exposed it that
        way. Reading it through the catalogue keeps every existing consumer working while the
        single source of truth becomes the foreign key — and it is derived, so it can never
        drift from the rung the curator actually chose.
        """
        return self.level_ref.name if self.level_ref else None

    @property
    def typology(self) -> str | None:
        """
        Name of the typology, derived from the foreign key on read.

        Same contract as ``level``: the client reads a name, the database stores an id, and the
        catalogue stays the single source of truth. It is what lets the read view expose the
        typology without the front-end resolving an id per row.
        """
        return self.typology_ref.name if self.typology_ref else None

    __table_args__ = (
        # The GIN index is vital for the AI Workers' polling performance
        Index("ix_archive_exec_log", execution_log, postgresql_using="gin"),
        # Native full-text search over the generated ``search_vector`` column.
        Index("ix_archive_documents_search_vector", "search_vector", postgresql_using="gin"),
        # Approximate nearest neighbour over the embeddings. HNSW needs no training
        # data (unlike IVFFlat) and keeps recall high as the collection grows.
        Index(
            "ix_archive_documents_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Subtree navigation (``path LIKE 'x.%'``). ``text_pattern_ops`` is required for the
        # index to be usable by ``LIKE`` under a non-C collation, which is the database's case.
        Index("ix_archive_documents_path", "path", postgresql_ops={"path": "text_pattern_ops"}),
    )


class ArchiveDocumentRevision(Base):
    """
    Audit trail of every human edit made to a document.

    Authorship is two columns and not one: ``changed_by`` is the name the history prints, and
    ``changed_by_user_id`` is the account behind it. The name is a snapshot — renaming somebody does
    not rewrite what they decided — and the id is what makes "everything this account did" a query
    instead of a text search. What the archivist actually decides is the *what*: the before/after of
    every field that changed, stored as JSONB, so a decision can be explained and reverted with
    evidence.
    """

    __tablename__ = "archive_document_revisions"

    revision_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("archive_documents.description_id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Free text until authentication exists; then it will carry the authenticated user.
    changed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )

    # ``{"scope_content": {"old": "...", "new": "..."}}`` — only the fields that changed.
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArchiveDocumentDeletion(Base):
    """
    Ledger of the one destructive write over the collection.

    **Exclusão definitiva tem guarda e tem trilha.** Two things make it defensible:

    * a node with children is refused (the self-referencing FK is ``RESTRICT``, because every
      descendant's materialised ``path`` carries its ancestors' ids — a silent delete would leave a
      whole subtree pointing at a prefix that no longer exists);
    * the row is **snapshotted here before it is deleted**, with the reference code, the title and the
      whole ISAD(G) content. The revision ledger cannot carry this: its FK is ``ON DELETE CASCADE``,
      so a revision written for a deleted document dies with it — an audit trail nobody can read is
      not an audit trail.

    There is deliberately **no foreign key** to ``archive_documents``: the row it names is gone by
    design, and this ledger is the thing that outlives it.
    """

    __tablename__ = "archive_document_deletions"

    deletion_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    description_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # The three fields a person uses to recognise the record; copied out so the ledger is readable
    # without opening the snapshot.
    reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    level_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Every ISAD(G) field of the deleted description, so the decision can be explained and the record
    # could be rebuilt by hand. Not a restore: there is no code path that writes it back.
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: How many descriptions the deleted node carried below it. Always 0 today, because a node with
    #: children is refused — the column exists so the guard's answer is part of the evidence.
    children_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Free text until authentication exists, as everywhere else in the curation writes.
    deleted_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    deleted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
