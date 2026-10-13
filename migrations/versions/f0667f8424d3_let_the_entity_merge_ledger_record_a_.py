"""let the entity merge ledger record a rename

A rename is the same class of write as a merge — it changes the name the extractor resolves and has
to be reversible — but it absorbs no entity, so the row has nothing to restore. ``kind`` is the
discriminator the undo branches on, and ``absorbed_*`` become nullable because a rename row has none
of them.

The three existing columns were ``NOT NULL`` and are all merges, so nothing is lost: the default
``MERGE`` fills every existing row with the truth, and the new check constraint is what stops a third
kind from reaching an undo that would try to restore an entity that never existed.

Revision ID: f0667f8424d3
Revises: c7d1e2f3a4b5
Create Date: 2026-10-13 15:05:50.154860

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f0667f8424d3"
down_revision: str | Sequence[str] | None = "c7d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "archive_entity_merge_log",
        sa.Column("kind", sa.String(length=20), server_default="MERGE", nullable=False),
    )
    op.create_check_constraint(
        "chk_entity_merge_log_kind",
        "archive_entity_merge_log",
        "kind IN ('MERGE', 'RENAME')",
    )
    op.alter_column("archive_entity_merge_log", "absorbed_entity_id", existing_type=sa.INTEGER(), nullable=True)
    op.alter_column("archive_entity_merge_log", "absorbed_name", existing_type=sa.VARCHAR(length=255), nullable=True)
    op.alter_column(
        "archive_entity_merge_log",
        "absorbed_snapshot",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # The rename rows have no absorbed entity, so they cannot survive the columns becoming NOT NULL
    # again: dropping them is the only honest reversal, and undo is not free in either direction.
    op.execute("DELETE FROM archive_entity_merge_log WHERE kind = 'RENAME'")
    op.alter_column(
        "archive_entity_merge_log",
        "absorbed_snapshot",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.alter_column("archive_entity_merge_log", "absorbed_name", existing_type=sa.VARCHAR(length=255), nullable=False)
    op.alter_column("archive_entity_merge_log", "absorbed_entity_id", existing_type=sa.INTEGER(), nullable=False)
    op.drop_constraint("chk_entity_merge_log_kind", "archive_entity_merge_log", type_="check")
    op.drop_column("archive_entity_merge_log", "kind")
