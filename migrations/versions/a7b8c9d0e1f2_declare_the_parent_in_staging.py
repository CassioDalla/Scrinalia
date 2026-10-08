"""declare the parent in staging

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-04 23:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Adds the arrangement the source declares, if it declares one.

    Both columns are nullable and no backfill is attempted, because the measurement is unambiguous:
    the origin does not send a parent today, which is exactly why the tree had to be derived from
    the reference codes in the first place. Making them optional is also the contract's point — an
    origin that stays silent must not break a load, and one that delivers a child before its parent
    must leave the child orphan and marked instead of failing the batch.
    """
    op.add_column("staging_documents", sa.Column("parent_reference_code", sa.Text(), nullable=True))
    op.add_column("staging_documents", sa.Column("hierarchy_path", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("staging_documents", "hierarchy_path")
    op.drop_column("staging_documents", "parent_reference_code")
