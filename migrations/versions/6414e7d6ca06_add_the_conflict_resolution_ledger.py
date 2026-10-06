"""add the conflict resolution ledger

`archive_conflict_resolution_log` is the write half of the tag x entity collision: the judge's
verdict already lives in `archive_ai_review_queue` (with no FK, because the pair can disappear),
and the resolution itself left no trace at all — neither the auto-resolved one nor the human one.
Without a ledger the transfer of documents and the deletion of the losing row were irreversible.

Both sides are snapshotted rather than referenced for the same reason the queue carries no FK: the
resolution deletes the loser, so a foreign key would be a promise the row cannot keep. The
composite index on the pair is what the read uses, once per row of the live scan, to answer "was
this pair already decided?".

Revision ID: 6414e7d6ca06
Revises: d1bc15fb6beb
Create Date: 2026-10-06 20:07:56.400984

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6414e7d6ca06"
down_revision: str | None = "d1bc15fb6beb"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "archive_conflict_resolution_log",
        sa.Column("resolution_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("winner", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=10), server_default="HUMAN", nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("tag_name", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("entity_name", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("loser_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("transferred_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_link_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ban_kind", sa.String(length=20), nullable=True),
        sa.Column("ban_term", sa.String(length=255), nullable=True),
        sa.Column("ban_created", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("decided_by", sa.String(length=100), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "ban_kind IS NULL OR ban_kind IN ('NER_EXCLUSION', 'STOPWORD')",
            name="chk_conflict_resolution_ban_kind",
        ),
        sa.CheckConstraint("source IN ('JUDGE', 'HUMAN')", name="chk_conflict_resolution_source"),
        sa.CheckConstraint("winner IN ('TAG', 'ENTITY')", name="chk_conflict_resolution_winner"),
        sa.PrimaryKeyConstraint("resolution_id"),
    )
    op.create_index(
        op.f("ix_archive_conflict_resolution_log_entity_id"),
        "archive_conflict_resolution_log",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_archive_conflict_resolution_log_tag_id"),
        "archive_conflict_resolution_log",
        ["tag_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_archive_conflict_resolution_log_winner"),
        "archive_conflict_resolution_log",
        ["winner"],
        unique=False,
    )
    op.create_index(
        "ix_conflict_resolution_pair", "archive_conflict_resolution_log", ["tag_id", "entity_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_conflict_resolution_pair", table_name="archive_conflict_resolution_log")
    op.drop_index(op.f("ix_archive_conflict_resolution_log_winner"), table_name="archive_conflict_resolution_log")
    op.drop_index(op.f("ix_archive_conflict_resolution_log_tag_id"), table_name="archive_conflict_resolution_log")
    op.drop_index(op.f("ix_archive_conflict_resolution_log_entity_id"), table_name="archive_conflict_resolution_log")
    op.drop_table("archive_conflict_resolution_log")
