from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from memoria_curitibana.core.base import Base

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
    llm_confidence: Mapped[str | None] = mapped_column(Float, nullable=True)
    llm_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("rule_kind IN ('REWRITE', 'VALIDATE', 'LLM_CHECK')", name="chk_cleaning_rule_kind"),
    )
