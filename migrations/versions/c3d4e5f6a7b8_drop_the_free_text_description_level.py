"""drop the free-text description level

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-04 21:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Removes ``archive_documents.level``, guarded.

    The free text has no reader left: the API, the archivist review and the transfer all speak
    ``level_id`` now, and the level's name is read through the catalogue. But the column is the
    archivist's declaration, and dropping it while a single row failed to map would destroy the
    only copy of that declaration. So the revision **refuses to run** in that case instead of
    dropping silently: an unmapped spelling is a curation decision (register the alias or map
    the value), not something a migration may discard.
    """
    connection = op.get_bind()
    unmapped = connection.execute(
        sa.text(
            """
            SELECT count(*)
              FROM archive_documents
             WHERE level_id IS NULL
               AND level IS NOT NULL
            """
        )
    ).scalar_one()

    if unmapped:
        raise RuntimeError(
            f"{unmapped} descriptions declare a level the catalogue does not know. "
            "Map them (or register the spelling as an alias) before dropping archive_documents.level: "
            "dropping now would destroy the only copy of the declaration."
        )

    op.drop_column("archive_documents", "level")


def downgrade() -> None:
    """
    Restores the free text from the catalogue.

    Round-trips without loss as long as the catalogue still holds the levels: the text column
    is exactly the ``name`` of the rung each description points at.
    """
    op.add_column("archive_documents", sa.Column("level", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE archive_documents AS d
               SET level = m.name
              FROM archive_description_levels AS m
             WHERE d.level_id = m.level_id
            """
        )
    )
