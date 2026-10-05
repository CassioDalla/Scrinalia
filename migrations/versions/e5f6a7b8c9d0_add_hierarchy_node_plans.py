"""add the hierarchy node plans

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-04 22:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Creates the catalogue of arrangement rungs and the decisions about them.

    It has to be a table and not a computation because the code cannot be trusted alone: the
    canonical case is ``BR PRADAP SMU ED AL CONSTR``, where two alphabetic segments are **one**
    level of the arrangement ("Alvenaria - Construções"). Nothing in the string says so, so the
    archivist says it — and the decision has to outlive the suggestion run that produced the rung,
    or the same names would be asked again on every run.
    """
    op.create_table(
        "archive_hierarchy_node_plans",
        sa.Column("plan_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=500), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("parent_code", sa.String(length=500), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("declared_levels", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("flags", postgresql.ARRAY(sa.String(length=40)), nullable=False, server_default="{}"),
        sa.Column("sample_description_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("existing_description_id", sa.String(length=50), nullable=True),
        sa.Column("level_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("reference_code", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="SUGGESTED"),
        sa.Column("collapse_into_code", sa.String(length=500), nullable=True),
        sa.Column("decided_by", sa.String(length=100), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("materialised_description_id", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('SUGGESTED', 'APPROVED', 'REJECTED')", name="chk_hierarchy_plan_status"),
        sa.ForeignKeyConstraint(["level_id"], ["archive_description_levels.level_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("plan_id"),
        sa.UniqueConstraint("code", name="uq_hierarchy_plan_code"),
    )
    op.create_index("ix_archive_hierarchy_node_plans_code", "archive_hierarchy_node_plans", ["code"])
    op.create_index("ix_archive_hierarchy_node_plans_status", "archive_hierarchy_node_plans", ["status"])
    op.create_index("ix_archive_hierarchy_node_plans_level_id", "archive_hierarchy_node_plans", ["level_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_archive_hierarchy_node_plans_level_id", table_name="archive_hierarchy_node_plans")
    op.drop_index("ix_archive_hierarchy_node_plans_status", table_name="archive_hierarchy_node_plans")
    op.drop_index("ix_archive_hierarchy_node_plans_code", table_name="archive_hierarchy_node_plans")
    op.drop_table("archive_hierarchy_node_plans")
