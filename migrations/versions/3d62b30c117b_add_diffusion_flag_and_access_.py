"""add diffusion flag and access conditions to the archive document

Revision ID: 3d62b30c117b
Revises: a7b8c9d0e1f2
Create Date: 2026-10-05 15:05:19.390385

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d62b30c117b"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Closes a silent data loss and opens the diffusion axis.

    ``access_conditions`` (ISAD(G) 4.1) was parsed into staging and never transferred: the archive
    had no column for it, so a restriction declared by the origin disappeared on the way in. It is
    nullable with no backfill because the value only exists from now on — the previous loads did
    not carry it forward, and inventing a default would be stating a legal condition nobody wrote.

    ``is_published`` is the institution's diffusion decision, deliberately kept apart from
    ``review_status``: publishing must not lock a record against AI rewriting, which is what
    reusing ``HUMAN_APPROVED`` as the predicate would have done. It has a server default because
    the table is not empty: 3 608 existing rows are not published, and a NOT NULL column without a
    default cannot be added to them.
    """
    op.add_column("archive_documents", sa.Column("access_conditions", sa.Text(), nullable=True))
    op.add_column(
        "archive_documents",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(op.f("ix_archive_documents_is_published"), "archive_documents", ["is_published"], unique=False)


def downgrade() -> None:
    """Drops the diffusion axis and the access condition; both are additions with no dependants."""
    op.drop_index(op.f("ix_archive_documents_is_published"), table_name="archive_documents")
    op.drop_column("archive_documents", "is_published")
    op.drop_column("archive_documents", "access_conditions")
