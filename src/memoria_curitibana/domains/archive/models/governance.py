from datetime import datetime

from sqlalchemy import (
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


class ArchiveCleaningRule(Base):
    """
    Table that stores the dynamic cleaning rules (Regex) created by users.
    """

    __tablename__ = "archive_cleaning_rules"

    rule_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String(150), nullable=False)

    # E.g.: "original_title", "scope_content"
    target_column: Mapped[str] = mapped_column(String(50), nullable=False)

    # E.g.: r"\b(av\.?\s+avenida)\b"
    regex_pattern: Mapped[str] = mapped_column(Text, nullable=False)

    # E.g.: "Avenida" (If empty, acts as an exclusion)
    replacement_string: Mapped[str] = mapped_column(Text, default="", server_default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Tracks who created it
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
