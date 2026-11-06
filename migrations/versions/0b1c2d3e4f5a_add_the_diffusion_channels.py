"""add the diffusion channels

Revision ID: 0b1c2d3e4f5a
Revises: f4ac6a4c4d09
Create Date: 2026-10-29 14:30:00.000000

ADR 0023 makes a diffusion channel a definition in code plus a lifecycle row, the mirror of the
origin (ADR 0016). The table holds what an operator changes without a deploy: whether the channel is
enabled, its configuration, the run policy an export inherits, and the agenda. There is **no seed**:
a fresh installation has no channel, and the operator page's empty state is real.

The registry code is not a foreign key: channels are code, and a row whose code left the registry
stays readable — it simply cannot be used.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0b1c2d3e4f5a"
down_revision: str | Sequence[str] | None = "f4ac6a4c4d09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Creates the channel lifecycle table and its agenda index."""
    op.create_table(
        "diffusion_channels",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cron", sa.String(length=120), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_skipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("code"),
    )
    # The scheduler's due query (#212): enabled channels with an agenda whose next run is due.
    op.create_index("ix_diffusion_channel_next_run_at", "diffusion_channels", ["next_run_at"])


def downgrade() -> None:
    """Drops the table; the channel definitions are code and survive, the rows do not."""
    op.drop_index("ix_diffusion_channel_next_run_at", table_name="diffusion_channels")
    op.drop_table("diffusion_channels")
