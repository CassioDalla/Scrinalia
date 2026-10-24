"""the entity link records its origin

Issue #135: ``archive_document_entities`` was a bare composite key, so a surviving link could not
say whether the extractor wrote it and nobody looked, or whether a person had confirmed it. The
column is additive and the existing rows are ``UNKNOWN`` — not ``AI``: the database cannot prove
which producer wrote them, and a migration that guessed would invent the very fact the column
exists to keep.

Measured on the reference collection (``memoriacuritibana``) before the migration: **64,504** links
over **4,811** documents; ``archive_document_revisions`` holds **0** rows and no item is
``HUMAN_APPROVED``, so there is no human link to protect and nothing to infer from history.

``created_at`` is nullable on purpose: stamping "now" on the rows that predate the column would be
the same invention in another field.

Revision ID: b4e2c8d17a63
Revises: e55c7ac89985
Create Date: 2026-10-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4e2c8d17a63"
down_revision: str | Sequence[str] | None = "e55c7ac89985"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The type name and its members. Spelled out instead of imported: a migration is a snapshot of the
#: schema at its revision, and importing the application's vocabulary would make it stop being one
#: the day that vocabulary moves.
ORIGIN_TYPE = "archive_entity_origin"


def upgrade() -> None:
    """Add the origin and the moment to the link, and backfill the honest value."""
    op.execute(f"CREATE TYPE {ORIGIN_TYPE} AS ENUM ('AI', 'HUMAN', 'UNKNOWN')")
    op.add_column(
        "archive_document_entities",
        sa.Column("origin", postgresql.ENUM(name=ORIGIN_TYPE, create_type=False), nullable=True),
    )
    op.add_column(
        "archive_document_entities",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE archive_document_entities SET origin = 'UNKNOWN'")
    op.alter_column("archive_document_entities", "origin", nullable=False)


def downgrade() -> None:
    """Drop the two columns and the type, keeping the links themselves."""
    op.drop_column("archive_document_entities", "created_at")
    op.drop_column("archive_document_entities", "origin")
    op.execute(f"DROP TYPE {ORIGIN_TYPE}")
