"""add the diffusion publication scopes

Revision ID: 9f2a7c1e5b30
Revises: c3f8a1d2e4b6
Create Date: 2026-10-30 11:30:00.000000

ADR 0023 makes a record exposed through a scope, not a boolean: a positive scope says "this branch
or record goes to this channel", a negative one says "this branch or record stays out of it". Both
tables have the same shape on purpose — ``include_descendants``, the author and the revocation
columns — so the predicate reads as one decision with two signs, and the exclusion adds only the
reason the curator gave.

Nothing here publishes a record by itself: the coverage is a read over these rows, the documents'
materialised ``path`` and the approval, in the view the next revision creates. A revoked scope stays
in the table (``revoked_at``), because the ledger has to answer "who published this" after the
decision was reversed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "9f2a7c1e5b30"
down_revision: str | Sequence[str] | None = "c3f8a1d2e4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def _scope_table(name: str, index_prefix: str, text_column: str) -> None:
    """Creates one scope table; the two signs differ only in the column that explains the decision."""
    op.create_table(
        name,
        sa.Column("scope_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("channel_code", sa.String(length=50), nullable=False),
        sa.Column("node_id", sa.String(length=50), nullable=False),
        sa.Column("include_descendants", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(text_column, sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=120), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["channel_code"], ["diffusion_channels.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["node_id"], ["archive_documents.description_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("scope_id"),
    )
    # A second active scope on the same node and channel is impossible; a revoked one does not block
    # a new decision, which is why the index is partial.
    op.create_index(
        f"uq_{index_prefix}_active",
        name,
        ["channel_code", "node_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    # The coverage view reads the active scopes of one channel.
    op.create_index(
        f"ix_{index_prefix}_channel",
        name,
        ["channel_code"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(f"ix_{index_prefix}_node", name, ["node_id"])


def upgrade() -> None:
    """Creates the two scope tables and the indexes the coverage read needs."""
    _scope_table("diffusion_channel_scopes", "diffusion_channel_scope", "note")
    _scope_table("diffusion_channel_exclusions", "diffusion_channel_exclusion", "reason")


def downgrade() -> None:
    """Drops both tables; the batches' entries keep the snapshot they recorded."""
    for name, index_prefix in (
        ("diffusion_channel_exclusions", "diffusion_channel_exclusion"),
        ("diffusion_channel_scopes", "diffusion_channel_scope"),
    ):
        op.drop_index(f"ix_{index_prefix}_node", table_name=name)
        op.drop_index(f"ix_{index_prefix}_channel", table_name=name)
        op.drop_index(f"uq_{index_prefix}_active", table_name=name)
        op.drop_table(name)
