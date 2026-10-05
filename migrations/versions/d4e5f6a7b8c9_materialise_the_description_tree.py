"""materialise the description tree

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-04 21:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Adds the self-reference and the materialised path, and makes every description a root.

    The collection is hierarchical but no link exists today: the measurement found **zero**
    descriptions whose reference code has an ancestor that is itself a record, so the honest
    starting state is a forest of roots — each node's path is its own id. The tree is
    materialised later, by the proposal (H3) and the archivist's approval (H4), not invented
    here.

    ``RESTRICT`` on the self-reference, not ``SET NULL``: every descendant's path carries its
    ancestors' ids, so a silent ``SET NULL`` would leave a whole subtree pointing at a prefix
    that no longer exists. A node with children is not deletable in passing.

    ``path`` is added nullable, backfilled from the primary key and only then made ``NOT NULL``:
    the three steps fit in one revision because the backfill covers every existing row, but they
    stay separate statements so a failure is legible.
    """
    op.add_column("archive_documents", sa.Column("parent_id", sa.String(length=50), nullable=True))
    op.add_column("archive_documents", sa.Column("path", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_archive_documents_parent_id",
        "archive_documents",
        "archive_documents",
        ["parent_id"],
        ["description_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_archive_documents_parent_id", "archive_documents", ["parent_id"], unique=False)

    op.execute("UPDATE archive_documents SET path = description_id WHERE path IS NULL")
    op.alter_column("archive_documents", "path", nullable=False)

    # ``text_pattern_ops`` is what makes ``path LIKE 'x.%'`` able to use the index under a
    # non-C collation, which is the database's case. Without it the subtree query — the one the
    # tree navigation makes constantly — degrades to a sequential scan.
    op.create_index(
        "ix_archive_documents_path",
        "archive_documents",
        ["path"],
        unique=False,
        postgresql_ops={"path": "text_pattern_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_archive_documents_path", table_name="archive_documents")
    op.drop_index("ix_archive_documents_parent_id", table_name="archive_documents")
    op.drop_constraint("fk_archive_documents_parent_id", "archive_documents", type_="foreignkey")
    op.drop_column("archive_documents", "path")
    op.drop_column("archive_documents", "parent_id")
