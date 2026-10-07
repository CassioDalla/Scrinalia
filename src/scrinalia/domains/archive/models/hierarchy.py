from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ARRAY, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scrinalia.core.base import Base

if TYPE_CHECKING:
    from .document import ArchiveDocument


class ArchiveDescriptionLevel(Base):
    """
    Catalogue of description levels (the NOBRADE/ISAD(G) ladder), owned by the archivist.

    The ladder is a table and not an enum because the norm is only the seed: NOBRADE runs from
    the *Acervo da entidade custodiadora* (0) down to the *Item documental* (5), but a curator
    may add or rename a rung without a deploy. ``code`` is the stable machine key the proposal
    and the API speak; ``name`` is the text the archivist (and the source) sees.

    ``name`` is deliberately seeded with **the spelling the source actually declares**
    (``"Item Documental"``, ``"Dossiê/Processo"``), not with the wording of the norm. The
    migration matches the ``level`` text of 3,608 real descriptions against it, and seeding
    ``"Item documental"`` would have failed every one of the 2,478 items on capitalisation
    alone. The norm's wording lives in ``description``; ``aliases`` is where the curator
    registers the spellings the normaliser must accept besides the canonical ``name``.

    ``requires_parent`` is the roadmap's ``is_required`` with the ambiguity removed: a node at
    this level may not be a root (a Dossiê only exists under something). It is **not** "every
    description must have this level". ``allows_children`` is the opposite end: an Item is a
    leaf, so giving it a child is a validation error, not a convention.
    """

    __tablename__ = "archive_description_levels"

    level_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: Position on the ladder. Not capped at 5: the seed has six rungs, but the catalogue is
    #: the archivist's, and a CHECK ceiling would turn "add a sub-level" into a migration.
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Alternative spellings accepted by ``domain.level_catalog`` when matching source text.
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default="{}")

    requires_parent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    allows_children: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(back_populates="level_ref")

    __table_args__ = (CheckConstraint("ordinal >= 0", name="chk_description_level_ordinal"),)


class ArchiveHierarchyNodePlan(Base):
    """
    One rung the reference codes imply, and the archivist's decision about it.

    Exists because the codes cannot be trusted alone. The measurement gave the canonical example:
    ``BR PRADAP SMU ED AL CONSTR`` splits into two alphabetic segments that are, in the real
    arrangement, **one** level ("Alvenaria - Construções") — and no slicer can know that, because
    the evidence is not in the string. So the machine proposes and the human disposes, and the
    disposition has to outlive the run that produced it: approving a rung must not be asked again
    on the next suggestion, exactly like the tag-merge catalogue.

    ``code`` is the fingerprint (the normalized rung), which makes the suggestion idempotent. The
    evidence columns are refreshed while the row is ``SUGGESTED`` and frozen afterwards, while
    ``level_id``/``title``/``reference_code`` stop being a proposal and become a decision the
    moment ``status`` leaves ``SUGGESTED``.

    ``collapse_into_code`` is the operation the code cannot do for itself: two alphabetic segments
    that are one rung (``AL`` + ``CONSTR``), or a rung whose documents really belong under an
    existing record that is spelled one letter differently (``FOTOGRAFIA`` vs the Série
    ``FOTOGRAFIAS``). Nothing is merged by similarity: the link is written by a person.
    """

    __tablename__ = "archive_hierarchy_node_plans"

    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Unique as a constraint plus a plain index, which is what the migration creates: the two
    # are different objects and ``unique=True, index=True`` would emit a single unique index.
    code: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Evidence from the last suggestion run (refreshed while SUGGESTED) ---
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    declared_levels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list, server_default="{}")
    flags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list, server_default="{}")
    sample_description_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    #: The record whose ``reference_code`` is exactly this code, when there is one. Its presence is
    #: what turns "create a node" into "adopt this description as the node".
    existing_description_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Proposal, then decision ---
    level_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_description_levels.level_id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    reference_code: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SUGGESTED", server_default="SUGGESTED", index=True
    )
    #: This rung is the same rung as ``collapse_into_code``. Advisory structure: the apply follows
    #: the links to their end, with a cycle guard.
    collapse_into_code: Mapped[str | None] = mapped_column(String(500), nullable=True)

    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    decided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: What the materialisation created or adopted for this plan. ``NULL`` means "not materialised".
    materialised_description_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('SUGGESTED', 'APPROVED', 'REJECTED')", name="chk_hierarchy_plan_status"),
        Index("ix_archive_hierarchy_node_plans_code", "code"),
    )


class ArchiveHierarchyMaterialisationLog(Base):
    """
    Ledger of one materialisation run, with enough detail to reverse it.

    The promise the curation flow makes — "a decision a human took, a human can undo" — needs the
    exact previous state, not an approximation of it: the node a description hung from before, and
    the path it had. ``previous_state`` is therefore ``{description_id: {parent_id, path}}`` for
    exactly the rows the run changed, and ``created_nodes`` lists the descriptions the run brought
    into existence so the undo can remove them after restoring their children.

    ``undone_at`` makes the undo single-shot and keeps the trail readable: the row is never
    deleted, so "this rung was materialised, then reversed" survives the reversal.
    """

    __tablename__ = "archive_hierarchy_materialisation_log"

    materialisation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: ``[{"description_id": ..., "code": ..., "level_id": ..., "title": ...}]``
    created_nodes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: ``{"<code>": "<description_id>"}`` — the rung each code resolved to in this run.
    rung_map: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: ``{"<description_id>": {"parent_id": ..., "path": ...}}`` for every row the run changed.
    previous_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    changed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The account behind the name above, exactly like every other authorship in the schema.
    undone_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
