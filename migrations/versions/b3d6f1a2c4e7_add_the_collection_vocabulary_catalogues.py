"""add the collection vocabulary catalogues

Revision ID: b3d6f1a2c4e7
Revises: fe7fcab37207
Create Date: 2026-10-07 17:05:00.000000

This revision used to seed the reference collection's vocabulary, and it no longer does. The rows are
**collection data** and do not belong in the repository, so they left: a fresh install creates the
two catalogues empty, and `python -m scrinalia.domains.archive.cli import` brings a file in when an
installation wants the vocabulary it came from.

Editing an applied revision is normally the wrong move, and it is right here for the reason that
matters: the data is not a schema change, and leaving the seed in would mean shipping the collection
in the one place a `git clone` always brings. An installation that already ran the previous form
keeps its rows — they are now that installation's data, which is exactly where they belong — and a
fresh one starts empty. The two converge in behaviour, because nothing reads the seed at runtime.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d6f1a2c4e7"
down_revision: str | Sequence[str] | None = "fe7fcab37207"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Creates the two vocabulary catalogues, empty.

    The catalogue replaces two constants that were read at runtime: the arrangement token map the
    hierarchy proposal suggested names from, and the regex of the collection's places and person names
    the subject guard refused. Reading them from rows is what lets another institution replace them
    without editing the software — and it is also what makes "no vocabulary" a valid state instead of
    a broken one. The guard refuses nothing of its own when the catalogue is empty, and the proposal
    suggests no names; neither falls back to the collection this project was built against.
    """
    op.create_table(
        "archive_arrangement_vocabulary",
        sa.Column("term_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("term_id"),
        sa.UniqueConstraint("token", name="uq_archive_arrangement_vocabulary_token"),
    )
    op.create_table(
        "archive_collection_terms",
        sa.Column("term_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("term", sa.String(length=200), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "DISTRICT",
                "MUNICIPALITY",
                "STATE",
                "REGION",
                "COUNTRY",
                "PERSON",
                name="collection_term_kind",
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("term_id"),
        sa.UniqueConstraint("term", "kind", name="uq_archive_collection_terms_term_kind"),
    )
    op.create_index("ix_archive_collection_terms_term", "archive_collection_terms", ["term"])


def downgrade() -> None:
    """
    Drops both catalogues.

    What that destroys is the installation's own vocabulary — every row, including whatever the
    archivist typed — and this migration cannot give it back, because the rows are not in the
    repository. Stating that plainly is the point: ``export`` before a downgrade is the difference
    between an inconvenience and losing the catalogue.
    """
    op.drop_index("ix_archive_collection_terms_term", table_name="archive_collection_terms")
    op.drop_table("archive_collection_terms")
    op.drop_table("archive_arrangement_vocabulary")
    sa.Enum(name="collection_term_kind").drop(op.get_bind(), checkfirst=True)
