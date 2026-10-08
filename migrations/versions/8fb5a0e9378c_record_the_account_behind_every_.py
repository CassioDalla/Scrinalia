"""record the account behind every authorship

Every ledger in this schema records *who* acted in a free-text column — ``changed_by``,
``decided_by``, ``deleted_by``, ``created_by``, ``requested_by`` — and the API used to take that text
from the request. Authentication closes the hole, and closing it makes a second column necessary
rather than nice: the name is what the history prints and it is a **snapshot** (renaming somebody must
not rewrite what they decided), while the id is the durable link that makes "everything this account
did" a query instead of a text search.

The text columns are untouched and are not backfilled. Rows written before this revision have an
author's name and no account, and that is the honest state: the name was a claim the client made, and
inventing an id for it would turn a claim into a fact.

Twelve foreign keys and **no indexes**, deliberately. The only query an index would serve is "what did
this account do", which nothing reads yet, and an account is never deleted (it is deactivated), so the
``ON DELETE SET NULL`` that would need one to stay cheap never fires. Adding the index when a screen
needs it is a one-line migration; carrying twelve unused ones is a cost on every write.

Revision ID: 8fb5a0e9378c
Revises: 88938f868a6e
Create Date: 2026-10-07 20:00:59.253483

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8fb5a0e9378c"
down_revision: str | Sequence[str] | None = "88938f868a6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ``(table, column)``. One list, iterated by both directions, so the upgrade and the downgrade
#: cannot disagree about which columns exist.
AUTHORSHIP_COLUMNS: tuple[tuple[str, str], ...] = (
    ("archive_cleaning_rules", "created_by_user_id"),
    ("archive_conflict_resolution_log", "decided_by_user_id"),
    ("archive_document_deletions", "deleted_by_user_id"),
    ("archive_document_revisions", "changed_by_user_id"),
    ("archive_hierarchy_materialisation_log", "changed_by_user_id"),
    ("archive_hierarchy_node_plans", "decided_by_user_id"),
    ("archive_tag_facets", "created_by_user_id"),
    ("archive_tag_merge_proposals", "decided_by_user_id"),
    ("archive_taxonomy_merge_log", "changed_by_user_id"),
    ("archive_worker_runs", "requested_by_user_id"),
    ("archive_worker_settings_revisions", "changed_by_user_id"),
    ("domain_text_templates", "created_by_user_id"),
)


def upgrade() -> None:
    """Add the account beside the name, on every ledger that records an author."""
    for table, column in AUTHORSHIP_COLUMNS:
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
    """Drop the links, keeping the names: the text columns were never touched by this revision."""
    for table, column in reversed(AUTHORSHIP_COLUMNS):
        op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")
        op.drop_column(table, column)
