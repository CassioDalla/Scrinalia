"""add the publication batch ledger

Revision ID: b7e3f9a1c852
Revises: a4c8d0e2f614
Create Date: 2026-10-30 11:34:00.000000

Principle VI: every write leaves a ledger that makes it reversible. A publication is one gesture —
publish a ramo, publish a selection, keep a record private, revoke a ramo — and the batch is its
reversible unit: the row names the action, the resolved selection, the counts and the author, and
the entries name each scope the gesture created or revoked, with the state before and after.

The entries keep the node snapshot (``node_id``, ``node_path``, ``node_title``) and deliberately have
no foreign key into ``archive_documents``: a node can be moved or deleted after the batch, and the
ledger still has to explain the decision. ``scope_id`` is a soft link for the same reason.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "b7e3f9a1c852"
down_revision: str | Sequence[str] | None = "a4c8d0e2f614"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Creates the batch and the entry tables; the entries cascade with their batch."""
    op.create_table(
        "diffusion_publication_batches",
        sa.Column("batch_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column(
            "selection",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("applied_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("skipped_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=120), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.String(length=120), nullable=True),
        sa.Column("undone_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "action IN ('PUBLISH', 'EXCLUDE', 'REVOKE', 'UNEXCLUDE')",
            name="chk_diffusion_publication_batch_action",
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["undone_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("batch_id"),
    )
    op.create_table(
        "diffusion_publication_entries",
        sa.Column("entry_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_code", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("scope_id", sa.BigInteger(), nullable=True),
        sa.Column("node_id", sa.String(length=50), nullable=False),
        sa.Column("node_path", sa.Text(), nullable=False),
        sa.Column("node_title", sa.Text(), nullable=True),
        sa.Column("include_descendants", sa.Boolean(), nullable=False),
        sa.Column("was_active", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('INCLUSION', 'EXCLUSION')", name="chk_diffusion_publication_entry_kind"),
        sa.ForeignKeyConstraint(["batch_id"], ["diffusion_publication_batches.batch_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entry_id"),
    )
    # The undo and the history read one batch's entries; the batch id is the only key they use.
    op.create_index("ix_diffusion_publication_entry_batch", "diffusion_publication_entries", ["batch_id"])


def downgrade() -> None:
    """Drops the ledger; the scopes it recorded are the evidence and stay."""
    op.drop_index("ix_diffusion_publication_entry_batch", table_name="diffusion_publication_entries")
    op.drop_table("diffusion_publication_entries")
    op.drop_table("diffusion_publication_batches")
