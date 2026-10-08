"""add the human review audit trail

Revision ID: c59132842dbe
Revises: cecb7bcf7f7d
Create Date: 2026-10-04 13:58:30.512588

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c59132842dbe"
down_revision: str | Sequence[str] | None = "cecb7bcf7f7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "archive_document_revisions",
        sa.Column("revision_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("description_id", sa.String(length=50), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["description_id"], ["archive_documents.description_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("revision_id"),
    )
    op.create_index(
        op.f("ix_archive_document_revisions_description_id"),
        "archive_document_revisions",
        ["description_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_archive_document_revisions_description_id"), table_name="archive_document_revisions")
    op.drop_table("archive_document_revisions")
