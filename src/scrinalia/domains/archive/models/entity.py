from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scrinalia.core.base import Base

# Type-checker only, and load-bearing: the ``Mapped[...]`` strings below need this name. Keeping it
# inside the guard is what makes CodeQL's ``py/unsafe-cyclic-import`` finding a false positive
# (dismissed); ``testing/unit/quality/test_model_import_cycles.py`` fails if the cycle becomes real.
if TYPE_CHECKING:
    from .document import ArchiveDocument


class ArchiveEntity(Base):
    """
    Named Entities (People, Organizations, Locations).
    Discovered dynamically by spaCy or inserted manually.
    """

    __tablename__ = "archive_entities"

    entity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(
        secondary="archive_document_entities", back_populates="entities"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "idx_archive_entities_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        # The identity rule ``normalize_entity`` already declares — strip + lower — enforced where a
        # second row could appear. The case-sensitive unique index on the column cannot see ``Batel``
        # and ``batel`` as one name; this one can, and it is what stops ``get_or_create_entities``
        # (which inserts the normalized spelling) from creating a twin of a row stored in Title Case.
        Index("uix_archive_entities_name_normalized", func.lower(func.btrim(name)), unique=True),
    )


class ArchiveEntityMergeLog(Base):
    """
    Ledger of every absorbed entity, with enough detail to undo the merge without loss.

    One row **per absorbed entity**, not per cluster: the unit of undo is the entity. The row
    keeps a full snapshot of the deleted entity (name, type, when it was created) and the exact
    documents that carried it, so the reverse operation restores the row and its links instead of
    an approximation of them. Nothing less would make the promise of the curation flow true: a
    merge approved by a human has to be revertible by a human.

    ``canonical_renamed_from`` captures the rename the same write applied to the canonical,
    because the optional rename is part of the merge and the undo has to put the old spelling
    back. ``canonical_entity_type`` is the ``category`` of the spellings this merge writes; it is
    snapshotted because the canonical can be reclassified before the undo runs.

    ``undone_at`` makes the undo single-shot and keeps the trail readable after the fact — the
    row is never deleted, so the history of "this was merged, then undone" survives.

    ``kind`` separates the two writes that share this ledger. A **merge** row absorbs an entity and
    has to restore it; a **rename** row only changed the canonical's spelling, so there is no absorbed
    entity and ``absorbed_*`` are ``None``. It is a discriminator and not a second table because the
    undo, the trail and the screen are the same for both, and a second ledger would be a second
    definition of "put the name back" — the drift principle IV exists to prevent.
    """

    __tablename__ = "archive_entity_merge_log"

    merge_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    #: ``MERGE`` or ``RENAME``; the undo branches on it. Existing rows predate the rename and are all
    #: merges, which is why the default is the merge and no backfill is needed.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="MERGE")

    # Snapshots: the canonical survives today, but it can be absorbed by a later merge, so what
    # undo restores must not depend on reading the current catalogue.
    canonical_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)

    #: ``None`` on a rename row: nothing was absorbed, so there is no row to bring back.
    absorbed_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    absorbed_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    absorbed_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Exactly the documents that carried the absorbed entity (a union would over-link on undo).
    document_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # The subset the merge newly linked to the canonical (i.e. the documents that did not have
    # it before). Undo removes exactly these links: restoring the entity without removing them
    # would leave the document with both spellings, which is not the pre-merge state.
    created_link_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # The spelling equal to the absorbed name was created by this merge (undo deletes it), or
    # already existed pointing somewhere else (undo moves it back to that place).
    synonym_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    synonym_previous_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Spellings that pointed *at* the absorbed entity and were moved to the canonical.
    repointed_synonym_names: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # The name the canonical carried before this merge renamed it (``None`` when it did not), and
    # the same spelling state for the old name the rename planted as a synonym.
    canonical_renamed_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    renamed_from_synonym_created: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    renamed_from_synonym_previous_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

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

    __table_args__ = (
        # A gate and not decoration: the undo branches on ``kind``, so a third value would fall into
        # the merge branch and try to restore an entity that never existed.
        CheckConstraint("kind IN ('MERGE', 'RENAME')", name="chk_entity_merge_log_kind"),
    )
