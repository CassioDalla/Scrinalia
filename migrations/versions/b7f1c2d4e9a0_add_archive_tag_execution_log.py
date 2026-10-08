"""add archive tag execution log

Revision ID: b7f1c2d4e9a0
Revises: a5cc7ec65348
Create Date: 2026-10-03 17:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7f1c2d4e9a0"
down_revision: str | Sequence[str] | None = "a5cc7ec65348"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("archive_tags", sa.Column("execution_log", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(
        "ix_archive_tags_exec_log",
        "archive_tags",
        ["execution_log"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_archive_tags_exec_log", table_name="archive_tags", postgresql_using="gin")
    op.drop_column("archive_tags", "execution_log")
