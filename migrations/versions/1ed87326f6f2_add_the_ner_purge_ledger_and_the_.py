"""add the NER purge ledger and the conflict spellings

Revision ID: 1ed87326f6f2
Revises: c47f5d81fef1
Create Date: 2026-10-13 19:27:05.144466

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1ed87326f6f2"
down_revision: str | Sequence[str] | None = "c47f5d81fef1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "archive_ner_purge_log",
        sa.Column("purge_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("excluded_term", sa.String(length=255), nullable=False),
        sa.Column("purged_entity_id", sa.Integer(), nullable=False),
        sa.Column("purged_name", sa.String(length=255), nullable=False),
        sa.Column("purged_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("synonym_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by", sa.String(length=100), nullable=True),
        sa.Column("undone_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["undone_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("purge_id"),
    )
    op.create_index(
        op.f("ix_archive_ner_purge_log_excluded_term"), "archive_ner_purge_log", ["excluded_term"], unique=False
    )
    op.create_index(
        op.f("ix_archive_ner_purge_log_purged_entity_id"), "archive_ner_purge_log", ["purged_entity_id"], unique=False
    )

    # The column arrives on a table that already has rows, so it is filled by a server default in the
    # same statement and the default is then dropped: the model carries no server default, and
    # leaving one behind would be drift ``alembic check`` reports on the next installation.
    op.add_column(
        "archive_conflict_resolution_log",
        sa.Column(
            "synonym_names",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("archive_conflict_resolution_log", "synonym_names", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("archive_conflict_resolution_log", "synonym_names")
    op.drop_index(op.f("ix_archive_ner_purge_log_purged_entity_id"), table_name="archive_ner_purge_log")
    op.drop_index(op.f("ix_archive_ner_purge_log_excluded_term"), table_name="archive_ner_purge_log")
    op.drop_table("archive_ner_purge_log")
