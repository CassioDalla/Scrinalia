"""add tag merge proposals

Revision ID: acfe0e1d9f1f
Revises: c59132842dbe
Create Date: 2026-10-04 16:56:31.315004

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "acfe0e1d9f1f"
down_revision: str | Sequence[str] | None = "c59132842dbe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "archive_tag_merge_proposals",
        sa.Column("proposal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("canonical_id", sa.Integer(), nullable=True),
        sa.Column("canonical_name", sa.String(length=100), nullable=False),
        sa.Column("members", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.String(length=10), server_default="MIXED", nullable=False),
        sa.Column("review_flags", sa.ARRAY(sa.String(length=40)), server_default="{}", nullable=False),
        sa.Column("total_documents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="SUGGESTED", nullable=False),
        sa.Column("decided_by", sa.String(length=100), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("reason IN ('TRIGRAM', 'PLURAL', 'MIXED')", name="chk_tag_merge_proposal_reason"),
        sa.CheckConstraint("status IN ('SUGGESTED', 'APPROVED', 'REJECTED')", name="chk_tag_merge_proposal_status"),
        sa.PrimaryKeyConstraint("proposal_id"),
    )
    op.create_index(
        op.f("ix_archive_tag_merge_proposals_fingerprint"),
        "archive_tag_merge_proposals",
        ["fingerprint"],
        unique=True,
    )
    op.create_index(
        op.f("ix_archive_tag_merge_proposals_status"),
        "archive_tag_merge_proposals",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_archive_tag_merge_proposals_status"), table_name="archive_tag_merge_proposals")
    op.drop_index(op.f("ix_archive_tag_merge_proposals_fingerprint"), table_name="archive_tag_merge_proposals")
    op.drop_table("archive_tag_merge_proposals")
