"""add text template catalog and quality rule kinds

Revision ID: c5b784678746
Revises: e7b2c4a91d38
Create Date: 2026-10-04 13:05:28.808675

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5b784678746"
down_revision: str | Sequence[str] | None = "e7b2c4a91d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "domain_text_templates",
        sa.Column("template_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("variants", sa.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("action", sa.String(length=10), server_default="IGNORE", nullable=False),
        sa.Column("replacement", sa.Text(), server_default="", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="HUMAN", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="SUGGESTED", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("occurrence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sample_document_ids", sa.ARRAY(sa.String(length=50)), server_default="{}", nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("action IN ('IGNORE', 'REPLACE')", name="chk_text_template_action"),
        sa.CheckConstraint("source IN ('SUGGESTED', 'HUMAN')", name="chk_text_template_source"),
        sa.CheckConstraint("status IN ('SUGGESTED', 'APPROVED', 'REJECTED')", name="chk_text_template_status"),
        sa.PrimaryKeyConstraint("template_id"),
    )
    op.create_index(op.f("ix_domain_text_templates_fingerprint"), "domain_text_templates", ["fingerprint"], unique=True)

    op.add_column(
        "archive_cleaning_rules",
        sa.Column("rule_kind", sa.String(length=20), server_default="REWRITE", nullable=False),
    )
    op.add_column("archive_cleaning_rules", sa.Column("anomaly_reason", sa.Text(), nullable=True))
    op.add_column("archive_cleaning_rules", sa.Column("engine_name", sa.String(length=50), nullable=True))
    op.add_column("archive_cleaning_rules", sa.Column("preset", sa.String(length=50), nullable=True))
    op.create_index(op.f("ix_archive_cleaning_rules_rule_kind"), "archive_cleaning_rules", ["rule_kind"], unique=False)
    op.create_check_constraint(
        "chk_cleaning_rule_kind",
        "archive_cleaning_rules",
        "rule_kind IN ('REWRITE', 'VALIDATE', 'LLM_CHECK')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("chk_cleaning_rule_kind", "archive_cleaning_rules", type_="check")
    op.drop_index(op.f("ix_archive_cleaning_rules_rule_kind"), table_name="archive_cleaning_rules")
    op.drop_column("archive_cleaning_rules", "preset")
    op.drop_column("archive_cleaning_rules", "engine_name")
    op.drop_column("archive_cleaning_rules", "anomaly_reason")
    op.drop_column("archive_cleaning_rules", "rule_kind")
    op.drop_index(op.f("ix_domain_text_templates_fingerprint"), table_name="domain_text_templates")
    op.drop_table("domain_text_templates")
