"""add the taxonomy merge ledger

Revision ID: 63bcc576d926
Revises: acfe0e1d9f1f
Create Date: 2026-10-04 17:17:56.653361

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "63bcc576d926"
down_revision: str | Sequence[str] | None = "acfe0e1d9f1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "archive_taxonomy_merge_log",
        sa.Column("merge_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cluster_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("canonical_id", sa.Integer(), nullable=True),
        sa.Column("canonical_name", sa.String(length=100), nullable=False),
        sa.Column("absorbed_tag_id", sa.Integer(), nullable=False),
        sa.Column("absorbed_name", sa.String(length=100), nullable=False),
        sa.Column("absorbed_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_link_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("synonym_created", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("synonym_previous_tag_id", sa.Integer(), nullable=True),
        sa.Column("repointed_synonym_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("merge_id"),
    )
    op.create_index(
        op.f("ix_archive_taxonomy_merge_log_absorbed_tag_id"),
        "archive_taxonomy_merge_log",
        ["absorbed_tag_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_archive_taxonomy_merge_log_canonical_id"),
        "archive_taxonomy_merge_log",
        ["canonical_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_archive_taxonomy_merge_log_cluster_fingerprint"),
        "archive_taxonomy_merge_log",
        ["cluster_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_archive_taxonomy_merge_log_cluster_fingerprint"), table_name="archive_taxonomy_merge_log")
    op.drop_index(op.f("ix_archive_taxonomy_merge_log_canonical_id"), table_name="archive_taxonomy_merge_log")
    op.drop_index(op.f("ix_archive_taxonomy_merge_log_absorbed_tag_id"), table_name="archive_taxonomy_merge_log")
    op.drop_table("archive_taxonomy_merge_log")
