"""add domain ner exclusions

Revision ID: 2f86264b563b
Revises: b7f1c2d4e9a0
Create Date: 2026-10-03 20:56:42.316803

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f86264b563b"
down_revision: str | Sequence[str] | None = "b7f1c2d4e9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "domain_ner_exclusions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="HUMAN", nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('JUDGE', 'HUMAN')", name="chk_ner_exclusion_source"),
        sa.ForeignKeyConstraint(["tag_id"], ["archive_tags.tag_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_domain_ner_exclusions_tag_id"), "domain_ner_exclusions", ["tag_id"], unique=False)
    op.create_index(op.f("ix_domain_ner_exclusions_term"), "domain_ner_exclusions", ["term"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_domain_ner_exclusions_term"), table_name="domain_ner_exclusions")
    op.drop_index(op.f("ix_domain_ner_exclusions_tag_id"), table_name="domain_ner_exclusions")
    op.drop_table("domain_ner_exclusions")
