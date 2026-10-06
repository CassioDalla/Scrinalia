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

    #: The hypothesis the curator writes for the NLI model, when the bare name is not enough.
    #:
    #: **Measured, and the measurement contradicts the intuition that created this column.**
    #: The hypothesis was "a noun phrase is not a proposition, so writing a sentence fixes the
    #: classification". On a 44-tag human-labelled set (B1/B3, ``testing/evaluation``), turning
    #: the label into a sentence scored **0.000** — zero correct answers out of 40 subject tags,
    #: on two models and two wordings, with 65% of them collapsing into a single drawer. The
    #: baseline it was supposed to beat is the bare name, at 0.500 (mDeBERTa) and 0.575
    #: (xlm-roberta). A mixed label set, where the sentence competes against bare names, makes
    #: the format look better (0.450) while still losing to the baseline: that arrangement is
    #: what the earlier plan most likely measured.
    #:
    #: So the column is a **curation escape hatch, not the default**. ``None`` — the bare name —
    #: is the measured best and stays the behaviour for every drawer nobody writes here. A
    #: curator who wants to try another wording can, and the hash-keyed stamp re-queues the
    #: tags by itself; but do not seed this column with sentences expecting an improvement.
    #:
    #: Whatever is written here is what the model reasons about, so it must stay a short
    #: statement about a subject, never the ``description`` below.
    classifier_label: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    # winner scored below the threshold is stamped and not retried forever. For the
    # content-keyed variant (``MACRO_CATEGORY``) the *value* is the hash of the label
    # set the tag was classified against, so rewriting a curator label re-queues it.
    execution_log: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(
        secondary="archive_document_tags", back_populates="tags"
    )
    macro_category: Mapped["ArchiveMacroCategory"] = relationship(back_populates="tags")
    facets: Mapped[list["ArchiveTagFacet"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan", passive_deletes=True
    )

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


class ArchiveTagFacet(Base):
    """
    The non-subject axis of a tag: what it *is*, when it is not an *about*.

    ``archive_tags.macro_category_id`` holds one subject drawer and nothing else. A tag like
    ``ippuc`` (2.376 documents) or ``curitiba`` (1.865) has no subject but is unmistakably a
    producer or a place; forcing them into the subject axis is a measured cause of the
    classification defect, because they competed with ``alvenaria`` for the same slot. This
    table is where those statements live instead.

    The primary key is ``(tag_id, facet_type)``: a tag can be a place *and* an institution,
    but not twice the same one. ``value`` carries the canonical spelling the curator chose,
    which is what the facets read — the tag name is the evidence, the value is the decision.
    Nothing writes here automatically: a facet is a curation act, never an AI inference.
    """

    __tablename__ = "archive_tag_facets"

    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archive_tags.tag_id", ondelete="CASCADE"), primary_key=True
    )
    facet_type: Mapped[str] = mapped_column(String(20), primary_key=True)

    #: The canonical value of the facet (``IPPUC``, ``Curitiba``). Falls back to the tag
    #: name when the curator only confirms the axis without renaming the spelling.
    value: Mapped[str] = mapped_column(String(100), nullable=False)

    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tag: Mapped["ArchiveTag"] = relationship(back_populates="facets")

    __table_args__ = (
        CheckConstraint("facet_type IN ('INSTITUTION', 'PLACE')", name="chk_tag_facet_type"),
        Index("ix_archive_tag_facets_type_value", facet_type, value),
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
        CheckConstraint(
            "status IN ('SUGGESTED', 'APPROVED', 'REJECTED', 'APPLIED')", name="chk_tag_merge_proposal_status"
        ),
        CheckConstraint("reason IN ('TRIGRAM', 'PLURAL', 'MIXED')", name="chk_tag_merge_proposal_reason"),
    )


class ArchiveTaxonomyMergeLog(Base):
    """
    Ledger of every absorbed tag, with enough detail to undo the merge without loss.

    One row **per absorbed tag**, not per cluster: the unit of undo is the tag. The row keeps
    a full snapshot of the deleted tag (name, category, confidence, the AI execution log) and
    the exact documents that carried it, so the reverse operation restores the row and its
    links instead of an approximation of them. Nothing less would make the promise of the
    curation flow true: a merge approved by a human has to be revertible by a human.

    ``undone_at`` makes the undo single-shot and keeps the trail readable after the fact —
    the row is never deleted, so the history of "this was merged, then undone" survives.
    ``synonym_*`` and ``repointed_synonym_names`` capture the spelling state *before* the
    merge, because the reverse has to restore what was there instead of guessing it.
    """

    __tablename__ = "archive_taxonomy_merge_log"

    merge_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The proposal that authorised this merge (null for an ad-hoc merge); grouping only,
    # deliberately not a foreign key so the ledger outlives the catalogue.
    cluster_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Snapshots: the canonical survives today, but it can be absorbed by a later merge, so
    # what undo restores must not depend on reading the current catalogue.
    canonical_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    canonical_name: Mapped[str] = mapped_column(String(100), nullable=False)

    absorbed_tag_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    absorbed_name: Mapped[str] = mapped_column(String(100), nullable=False)
    absorbed_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Exactly the documents that carried the absorbed tag (a union would over-link on undo).
    document_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # The subset the merge newly linked to the canonical (i.e. the documents that did not
    # have it before). Undo removes exactly these links: restoring the tag without removing
    # them would leave the document with both spellings, which is not the pre-merge state.
    created_link_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # The spelling equal to the absorbed name was created by this merge (undo deletes it), or
    # already existed pointing somewhere else (undo moves it back to that place).
    synonym_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    synonym_previous_tag_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Spellings that pointed *at* the absorbed tag and were moved to the canonical.
    repointed_synonym_names: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    changed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ArchiveTypology(Base):
    __tablename__ = "archive_typologies"

    typology_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    context_description: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["ArchiveDocument"]] = relationship(back_populates="typology_ref")
