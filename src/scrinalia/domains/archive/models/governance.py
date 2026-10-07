from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base

from .enums import AnomalyType, ArchiveReviewStatus, StopwordsScope


class DomainStopwords(Base):
    """List of stopwords specific to the archival
    domain for NLP cleaning."""

    __tablename__ = "domain_stopwords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    word_scope: Mapped[StopwordsScope] = mapped_column(
        Enum(StopwordsScope, name="stopwords_scope", create_type=False),
        default=StopwordsScope.TAG,
        nullable=False,
        index=True,
    )


class DomainSynonyms(Base):
    """
    Dictionary of synonyms for normalizing Entities and Tags.
    Maps variable terms ("pmc", "prefeituta") to a canonical entity or tag.
    """

    __tablename__ = "domain_synonyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The synonym name (e.g. "pmc", "prefeituta", "washington")
    synonym_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    # The Discriminator: Defines which universe this synonym belongs to
    # Accepted values: 'TAG', 'ORG', 'LOC', 'PER'
    category: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Exclusive Arcs: Optional foreign keys (Nullable)
    canonical_tag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_tags.tag_id", ondelete="CASCADE"), nullable=True
    )
    canonical_entity_id: Mapped[int | None] = mapped_column(
        Integer,
        # Verify that the table and column name of your entity is indeed this one
        ForeignKey("archive_entities.entity_id", ondelete="CASCADE"),
        nullable=True,
    )

    __table_args__ = (
        # 1. Ensures the same word can exist, AS LONG AS it is in different categories.
        # E.g.: "Amazon" (LOC) and "Amazon" (ORG) can coexist in peace.
        UniqueConstraint("synonym_name", "category", name="uix_synonym_category"),
        # 2. Data Integrity: Ensures in the PostgreSQL engine that we NEVER
        # have a row without a target, or a row pointing to both places at the same time.
        CheckConstraint(
            """
            (category = 'TAG' AND canonical_tag_id IS NOT NULL AND canonical_entity_id IS NULL) OR
            (category IN ('ORG', 'LOC', 'PER') AND canonical_entity_id IS NOT NULL AND canonical_tag_id IS NULL)
            """,
            name="chk_exclusive_synonym_target",
        ),
    )


class DomainNerExclusion(Base):
    """
    Terms the curation decided belong to the TAG axis, not to named entities.

    This is deliberately **not** a ``DomainStopwords`` row: a stopword is noise to be
    dropped from every extraction, while an exclusion is a *decision* that a
    legitimate term is owned by the subject axis. Keeping them apart is what lets a
    curator undo an exclusion without touching the generic blacklist, and is what
    gives the decision a traceable provenance: which tag justified it, and whether a
    human or the LLM judge decided.
    """

    __tablename__ = "domain_ner_exclusions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The extracted spelling, stored normalized to lowercase like entity names.
    term: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who decided: a human curator ("HUMAN") or the LLM conflict judge ("JUDGE").
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="HUMAN", server_default="HUMAN")

    # The tag that justifies the exclusion, when the decision came from a cross-domain
    # clash. ``SET NULL`` on purpose: deleting the tag must not silently re-open the
    # NER false positive this row exists to prevent.
    tag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_tags.tag_id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("source IN ('JUDGE', 'HUMAN')", name="chk_ner_exclusion_source"),)


class DomainSubjectExclusion(Base):
    """
    Terms the curation decided are not a *subject* at all.

    The deterministic guard in ``domain.vocabulary`` covers what has a recognisable **form**:
    a bare year, a placeholder, a street, a number with a unit. Measured against the labelled
    set it catches one of four non-subjects, because the rest are semantic judgements with no
    shape to match — ``pessoas`` (166 documents) is too generic to be an aboutness,
    ``vista aérea`` (89) is a photographic point of view, ``capanema`` (91) is a proper noun
    the guard has never seen. No rule reaches those, and the model cannot abstain: asked to
    choose, it chooses confidently and wrongly.

    So the second half of the class is a **decision**, and this table is where it lives —
    deliberately the same shape as :class:`DomainNerExclusion`, because the two are the same
    kind of statement about a different axis: "this term belongs to no subject drawer, and a
    human said so". Keeping it apart from ``DomainStopwords`` is what lets a curator undo it
    without touching the generic purge, and gives it provenance (``reason``, ``source``).

    Unlike ``DomainNerExclusion`` the verdict is not merely "do not extract": an excluded term
    must also never be **classified**, and it stays a tag of the collection, reachable by
    search. The exclusion silences the subject classifier, not the term.
    """

    __tablename__ = "domain_subject_exclusions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The tag spelling, normalized to lowercase like every other taxonomy key.
    term: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who decided: a human curator, or the deterministic guard recorded for auditability.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="HUMAN", server_default="HUMAN")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("source IN ('HUMAN', 'RULE')", name="chk_subject_exclusion_source"),)


class ArchiveAIReviewQueue(Base):
    """Unified queue for AI auditing. Stores context in JSONB."""

    __tablename__ = "archive_ai_review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    anomaly_type: Mapped[AnomalyType] = mapped_column(
        Enum(AnomalyType, name="anomaly_type_enum", create_type=False), nullable=False, index=True
    )

    status: Mapped[ArchiveReviewStatus] = mapped_column(
        Enum(ArchiveReviewStatus, name="archive_review_status_enum", create_type=False),
        default=ArchiveReviewStatus.PENDING_AI,
        nullable=False,
        index=True,
    )

    # Flexible payload: {"tag_id": 1, "entity_id": 2, "tag_name": "Batel"}
    context_payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Structured AI responses
    llm_decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ArchiveConflictResolutionLog(Base):
    """
    Ledger of every tag x entity resolution, with enough detail to undo it without loss.

    One row per resolution, and the unit of undo is the pair. It lives next to
    :class:`ArchiveAIReviewQueue` because the two are the two halves of the same operation: the
    queue keeps the *decision* (the judge's verdict, or the human's), this keeps the *write* —
    what was transferred, what was deleted, which ban was planted — so a decision a human took
    can be reversed by a human.

    Both sides are **snapshotted, not referenced**: the resolution deletes the loser, so a foreign
    key would be a promise the row cannot keep. The same reasoning as
    ``ArchiveTaxonomyMergeLog.absorbed_snapshot``, and the reason ``context_payload`` in the queue
    has no FK either.

    ``created_link_ids`` is what makes the undo exact rather than approximate. The resolution links
    the loser's documents to the winner with ``ON CONFLICT DO NOTHING``, so a document that already
    carried the winner keeps its link; without recording which links this resolution actually
    created, the undo would delete links that existed before it.

    ``ban_created`` is the same care applied to the governance write: the ban is planted with
    ``ON CONFLICT DO NOTHING``, so the undo must remove it only when this resolution is the one that
    planted it — otherwise reversing one resolution would lift a ban an earlier one decided.
    """

    __tablename__ = "archive_conflict_resolution_log"

    resolution_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: The axis that won. The loser's row is gone; the winner may be gone too, absorbed later.
    winner: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    #: Who decided: the judge worker auto-resolving, or a human on the conflict screen.
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="HUMAN", server_default="HUMAN")

    # The pair, as it was at decision time. Indexed so "was this spelling already decided?" is one
    # lookup rather than a scan of the ledger.
    tag_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tag_name: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)

    #: Full snapshot of the deleted row (every column plus ``created_at``), so the undo restores
    #: the row instead of an approximation of it.
    loser_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: Documents whose link was moved to the winner.
    transferred_document_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    #: The subset this resolution newly linked. The undo removes exactly these.
    created_link_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    #: The governance write in the winning axis: ``NER_EXCLUSION`` (tag won) or ``STOPWORD``
    #: (entity won), the spelling it names, and whether this resolution is what created it.
    ban_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ban_term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ban_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    decided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above, exactly like every other authorship in the schema.
    undone_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("winner IN ('TAG', 'ENTITY')", name="chk_conflict_resolution_winner"),
        CheckConstraint("source IN ('JUDGE', 'HUMAN')", name="chk_conflict_resolution_source"),
        CheckConstraint(
            "ban_kind IS NULL OR ban_kind IN ('NER_EXCLUSION', 'STOPWORD')",
            name="chk_conflict_resolution_ban_kind",
        ),
        # The read asks "was this pair already resolved?" once per row of the live scan, so the
        # pair is the key — the two single-column indexes only serve "everything about this tag".
        Index("ix_conflict_resolution_pair", "tag_id", "entity_id"),
    )


class DomainTextTemplate(Base):
    """
    Catalog of repeated excerpts the curation decided to keep out of the AI text.

    Same governance spirit as ``DomainNerExclusion``: a durable, auditable, reversible
    **decision**, never an automatic cleanup. The excerpts alone do not touch the
    archival record; they only change the text the AI reads, so the collection keeps its
    original ISAD(G) values and a human can undo the decision at any time.

    Why a row is not just ``(text, replacement)``:

    * ``fingerprint`` makes the catalog idempotent: the frequency routine can run again
      without duplicating what a human already approved. Two texts that differ only in
      whitespace are the same excerpt.
    * ``variants`` carries the near-duplicates found in the corpus ("cidadão,Liceu" vs
      "cidadão, Liceu"), so one decision removes every spelling instead of leaving two
      thirds of the boilerplate behind.
    * ``status`` separates "the machine proposed it" from "a human rejected it", which is
      what stops a re-run of the suggestion from resurrecting a discarded candidate.
    * ``occurrence_count``/``sample_document_ids`` are the numbers the archivist needs to
      decide; they are refreshed by the suggestion run and by the dry-run, never guessed.
    """

    __tablename__ = "domain_text_templates"

    template_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Canonical spelling of the excerpt, whitespace-normalized and trimmed.
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # SHA-256 of the normalized text. Unique so the suggestion routine is idempotent.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Additional spellings matched exactly like ``text``; near-duplicates of one decision.
    variants: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default="{}")

    # IGNORE subtracts the excerpt from the AI text; REPLACE substitutes ``replacement``.
    # A native enum was avoided on purpose: this is a catalog whose semantics may grow,
    # and the project already models ``DomainNerExclusion.source`` as String + check.
    action: Mapped[str] = mapped_column(String(10), nullable=False, default="IGNORE", server_default="IGNORE")
    replacement: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    # Who must stop reading the excerpt: ``EMBEDDING`` (the semantic vector), ``NER`` (the
    # text read by extraction and classification) and ``TITLE`` (the derived title
    # suggestion). The split exists because measurement showed one excerpt can help one
    # consumer and hurt another: removing the title prefix from the *embedded* text made
    # the ranking worse while being exactly what the title suggestion needs.
    scope: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, default=lambda: ["EMBEDDING", "NER"], server_default="{EMBEDDING,NER}"
    )

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who authored the row (``SUGGESTED`` by the frequency routine, ``HUMAN`` by a curator)
    # and where it is in the curation flow (``SUGGESTED`` -> ``APPROVED``/``REJECTED``).
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="HUMAN", server_default="HUMAN")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SUGGESTED", server_default="SUGGESTED")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # Evidence attached to the decision, so the archivist decides with a number.
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sample_document_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, default=list, server_default="{}"
    )

    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("action IN ('IGNORE', 'REPLACE')", name="chk_text_template_action"),
        CheckConstraint("source IN ('SUGGESTED', 'HUMAN')", name="chk_text_template_source"),
        CheckConstraint("status IN ('SUGGESTED', 'APPROVED', 'REJECTED')", name="chk_text_template_status"),
        CheckConstraint(
            "array_length(scope, 1) >= 1 AND scope <@ ARRAY['EMBEDDING', 'NER', 'TITLE']::varchar[]",
            name="chk_text_template_scope",
        ),
    )


class ArchiveCleaningRule(Base):
    """
    Table that stores the dynamic cleaning rules (Regex) created by users.
    """

    __tablename__ = "archive_cleaning_rules"

    rule_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String(150), nullable=False)

    # What the rule does. ``REWRITE`` is the original behaviour (the worker replaces every
    # match); ``VALIDATE`` only *flags* a match as an anomaly and never rewrites the text;
    # ``LLM_CHECK`` is the opt-in for the language-model check, which is off by default and
    # only runs while such a rule exists and is active.
    rule_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="REWRITE", server_default="REWRITE", index=True
    )

    # E.g.: "original_title", "scope_content"
    target_column: Mapped[str] = mapped_column(String(50), nullable=False)

    # E.g.: r"\b(av\.?\s+avenida)\b"
    regex_pattern: Mapped[str] = mapped_column(Text, nullable=False)

    # E.g.: "Avenida" (If empty, acts as an exclusion)
    replacement_string: Mapped[str] = mapped_column(Text, default="", server_default="")

    # Anomaly written to ``ArchiveDocument.anomaly_reasons`` when a VALIDATE rule matches.
    anomaly_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional engine/preset for an ``LLM_CHECK`` rule; ignored by the other kinds.
    engine_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preset: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Tracks who created it
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("rule_kind IN ('REWRITE', 'VALIDATE', 'LLM_CHECK')", name="chk_cleaning_rule_kind"),
    )
