"""record who undid a decision

The same two columns the previous revision added, for the third place a name was a claim the client
made: the three undo routes took ``undone_by`` from the query string, so "who reversed this" was
whatever the caller typed — and the reversal is precisely the act an archive most needs attributed,
because it is the one that removes a decision from the record.

The inventory that produced the previous revision searched for ``changed_by``, ``decided_by``,
``deleted_by``, ``created_by`` and ``requested_by``, and missed ``undone_by``. The defect was the same
and the fix is the same; this revision exists because the list was short, which is worth recording.

Text columns untouched, no backfill, and no indexes — for the same reasons as the previous revision.

Revision ID: e927d97c72a9
Revises: 8fb5a0e9378c
Create Date: 2026-10-07 20:31:05.441680

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e927d97c72a9"
down_revision: str | Sequence[str] | None = "8fb5a0e9378c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ``(table, column)``, iterated by both directions.
UNDO_COLUMNS: tuple[tuple[str, str], ...] = (
    ("archive_conflict_resolution_log", "undone_by_user_id"),
    ("archive_hierarchy_materialisation_log", "undone_by_user_id"),
    ("archive_taxonomy_merge_log", "undone_by_user_id"),
)


def upgrade() -> None:
    """Add the account beside the name on the three ledgers that record a reversal."""
    for table, column in UNDO_COLUMNS:
        op.add_column(table, sa.Column(column, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_{column}",
            table,
            "auth_users",
            [column],
            ["user_id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Drop the links, keeping the names."""
    for table, column in reversed(UNDO_COLUMNS):
        op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")
        op.drop_column(table, column)
