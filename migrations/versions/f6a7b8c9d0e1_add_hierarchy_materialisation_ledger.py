"""add the hierarchy materialisation ledger

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-04 22:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Creates the ledger of the materialisation runs.

    One row per run, not per node: the unit of reversal is the operation the archivist authorised.
    ``previous_state`` keeps the exact ``(parent_id, path)`` every changed description had before,
    because restoring the arrangement is not something that can be recomputed from the result — and
    ``created_nodes`` lists what the run brought into existence so the undo can remove it after
    restoring its children (the self-reference is ``RESTRICT``, so order matters).
    """
    op.create_table(
        "archive_hierarchy_materialisation_log",
        sa.Column("materialisation_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_nodes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rung_map", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("previous_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("materialisation_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("archive_hierarchy_materialisation_log")
