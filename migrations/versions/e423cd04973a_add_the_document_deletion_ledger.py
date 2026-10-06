"""add the document deletion ledger

Deleting a description is the only write in the curator UI that removes a record, and it had no trail.
The revision ledger cannot be that trail: its ``description_id`` is ``ON DELETE CASCADE``, so a
revision written for a deleted document is destroyed by the very delete it was recording — an audit
row nobody can read is not an audit row.

This table is the trail. It carries the three fields a person recognises a record by (reference code,
title, level), the **whole** ISAD(G) snapshot of the deleted row, who deleted it and why, and the
count of children the guard found (always zero today: a node with children is refused, because the
self-referencing FK is ``RESTRICT`` and every descendant's materialised ``path`` carries its
ancestors' ids).

There is deliberately no foreign key to ``archive_documents``: the row it names is gone by design, and
this ledger is the thing that outlives it.

Revision ID: e423cd04973a
Revises: a1b2c3d4e5f6
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e423cd04973a"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the deletion ledger."""
    op.create_table(
        "archive_document_deletions",
        sa.Column("deletion_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("description_id", sa.String(length=50), nullable=False),
        sa.Column("reference_code", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("level_name", sa.Text(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("children_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deleted_by", sa.String(length=100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("deletion_id"),
    )
    op.create_index(op.f("ix_archive_document_deletions_deleted_at"), "archive_document_deletions", ["deleted_at"])
    op.create_index(
        op.f("ix_archive_document_deletions_description_id"),
        "archive_document_deletions",
        ["description_id"],
    )


def downgrade() -> None:
    """Drop the deletion ledger, and the trail with it."""
    op.drop_index(op.f("ix_archive_document_deletions_description_id"), table_name="archive_document_deletions")
    op.drop_index(op.f("ix_archive_document_deletions_deleted_at"), table_name="archive_document_deletions")
    op.drop_table("archive_document_deletions")
