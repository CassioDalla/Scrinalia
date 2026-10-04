from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from memoria_curitibana.core.base import Base

if TYPE_CHECKING:
    from .document import ArchiveDocument


class ArchiveMacroCategory(Base):
    __tablename__ = "archive_macro_categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tags: Mapped[list["ArchiveTag"]] = relationship(back_populates="macro_category")


class ArchiveTag(Base):
    """
    Tags and Grouping Taxonomies.
    """

    __tablename__ = "archive_tags"

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    macro_category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_macro_categories.category_id", ondelete="SET NULL"), nullable=True, index=True
    )
    ai_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Idempotency ledger of the AI workers that processed this tag. Mirrors
    # ``ArchiveDocument.execution_log``: the pending query filters on the absence
    # of a versioned key instead of on nullable business columns, so a tag whose
    # winner scored below the threshold is stamped and not retried forever.
    execution_log: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(
        secondary="archive_document_tags", back_populates="tags"
    )
    macro_category: Mapped["ArchiveMacroCategory"] = relationship(back_populates="tags")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "idx_archive_tags_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        # GIN index used by the macro-category worker to poll unprocessed tags.
        Index("ix_archive_tags_exec_log", execution_log, postgresql_using="gin"),
    )


class ArchiveTagMergeProposal(Base):
    """
    A cluster of tags the routine proposes to unify, and the human decision about it.

    Suggestion only: the row is evidence plus a decision, never a merge. Approving records
    that the archivist accepted the cluster; applying it is a separate, logged operation
    (the ledger), so the decision is never confused with the write. ``fingerprint`` makes
    the suggestion idempotent — a re-run refreshes the evidence of a pending cluster and
    leaves an approved or rejected one exactly as the human left it, which is what stops
    the same hundreds of proposals from being re-reviewed on every run.

    ``canonical_id`` and ``members`` are *snapshots* and deliberately carry no foreign key:
    applying the proposal deletes those tags, and the proposal has to survive as the record
    of what was decided. The cluster is identified by its spellings, not by its ids.
    """

    __tablename__ = "archive_tag_merge_proposals"

    proposal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # SHA-256 of the canonical name plus the sorted member names. Unique: idempotent routine.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    canonical_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # [{"tag_id": 12, "name": "casas", "document_count": 3}, ...], canonical first.
    members: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    reason: Mapped[str] = mapped_column(String(10), nullable=False, default="MIXED", server_default="MIXED")

    # Warnings the curator should read before approving (``domain.tag_merge`` owns the codes).
    review_flags: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, default=list, server_default="{}"
    )

    # Union of the documents of the members: the evidence, never the sum (a document linked
    # to two members is one document).
    total_documents: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SUGGESTED", server_default="SUGGESTED", index=True
    )
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('SUGGESTED', 'APPROVED', 'REJECTED')", name="chk_tag_merge_proposal_status"),
        CheckConstraint("reason IN ('TRIGRAM', 'PLURAL', 'MIXED')", name="chk_tag_merge_proposal_reason"),
    )


class ArchiveTypology(Base):
    __tablename__ = "archive_typologies"

    typology_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    context_description: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["ArchiveDocument"]] = relationship(back_populates="typology")
