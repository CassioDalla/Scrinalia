"""add the entity merge ledger

Revision ID: c7d1e2f3a4b5
Revises: b8f066a47e7c
Create Date: 2026-10-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7d1e2f3a4b5"
down_revision: str | Sequence[str] | None = "b8f066a47e7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "archive_entity_merge_log",
        sa.Column("merge_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_id", sa.Integer(), nullable=True),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_entity_type", sa.String(length=50), nullable=False),
        sa.Column("absorbed_entity_id", sa.Integer(), nullable=False),
        sa.Column("absorbed_name", sa.String(length=255), nullable=False),
        sa.Column("absorbed_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_link_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("synonym_created", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("synonym_previous_entity_id", sa.Integer(), nullable=True),
        sa.Column("repointed_synonym_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_renamed_from", sa.String(length=255), nullable=True),
        sa.Column("renamed_from_synonym_created", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("renamed_from_synonym_previous_entity_id", sa.Integer(), nullable=True),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.String(length=100), nullable=True),
        sa.Column("undone_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["auth_users.user_id"],
            name="fk_archive_entity_merge_log_changed_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["undone_by_user_id"],
            ["auth_users.user_id"],
            name="fk_archive_entity_merge_log_undone_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("merge_id"),
    )
    op.create_index(
        op.f("ix_archive_entity_merge_log_absorbed_entity_id"),
        "archive_entity_merge_log",
        ["absorbed_entity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_archive_entity_merge_log_canonical_id"),
        "archive_entity_merge_log",
        ["canonical_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_archive_entity_merge_log_canonical_id"), table_name="archive_entity_merge_log")
    op.drop_index(op.f("ix_archive_entity_merge_log_absorbed_entity_id"), table_name="archive_entity_merge_log")
    op.drop_table("archive_entity_merge_log")
