"""add the stopword purge ledger

Revision ID: c47f5d81fef1
Revises: f0667f8424d3
Create Date: 2026-10-13 17:51:07.486097

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c47f5d81fef1"
down_revision: str | Sequence[str] | None = "f0667f8424d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "archive_stopword_purge_log",
        sa.Column("purge_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("purged_tag_id", sa.Integer(), nullable=False),
        sa.Column("purged_name", sa.String(length=100), nullable=False),
        sa.Column("purged_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("synonym_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.String(length=100), nullable=True),
        sa.Column("undone_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["undone_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("purge_id"),
    )
    op.create_index(
        op.f("ix_archive_stopword_purge_log_purged_tag_id"),
        "archive_stopword_purge_log",
        ["purged_tag_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_archive_stopword_purge_log_purged_tag_id"), table_name="archive_stopword_purge_log")
    op.drop_table("archive_stopword_purge_log")
