"""store the ISAD(G) record the transfer used to drop, and the date expression

Revision ID: e3084fbf75ba
Revises: 191c5f0a7b2e
Create Date: 2026-10-26 11:06:35.961808

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3084fbf75ba"
down_revision: str | Sequence[str] | None = "191c5f0a7b2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The columns the archive gains and the transfer will keep in sync from now on. Every one already
#: existed in ``staging_documents`` and was dropped by ``worker_archive_transfer``, so the backfill
#: below is an exact copy of what the staging layer parsed — not a guess.
BACKFILLED = (
    "dimension_support",
    "appraisal_destruction",
    "accruals",
    "arrangement",
    "reproduction_conditions",
    "physical_characteristics",
    "finding_aids",
    "originals_location",
    "copies_location",
    "related_units",
    "publication_notes",
    "conservation_notes",
    "general_notes",
    "rules_conventions",
    "description_dates",
    "parent_reference_code",
    "original_url",
)

#: ``date_expression`` is deliberately **not** in the backfill: it is a new column on
#: ``staging_documents`` too, so every existing staging row has it empty. Recovering the spelling
#: would mean reading each origin's date key out of ``raw_data.payload`` and applying the language's
#: placeholder rule in SQL — a second definition of the rule that lives in ``staging/dates.py``. The
#: expression fills itself the next time a record is parsed (``run_staging_pipeline(force=True)``
#: re-reads the raw payload), and until then the archive shows the parsed date it already had.
DATE_EXPRESSION = "date_expression"


def upgrade() -> None:
    """
    Gives the archive the whole ISAD(G) record, and the date as the source spells it.

    The staging transform has always parsed these fields; the transfer copied a subset, so the
    dossier could not show them and an archivist could not correct them. Each column is nullable and
    has no default: ``None`` means "the origin said nothing", which is a real state and not a value
    to invent.

    The backfill copies ``staging_documents`` into the new columns for every description that has a
    staging row, including the ``HUMAN_APPROVED`` ones: the columns were absent, not edited, and the
    content comes from the same source the review was made on. A description whose staging row no
    longer exists keeps them empty, which is visible and recoverable (the raw payload is intact).
    """
    op.add_column("archive_documents", sa.Column(DATE_EXPRESSION, sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("original_url", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("dimension_support", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("appraisal_destruction", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("accruals", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("arrangement", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("reproduction_conditions", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("physical_characteristics", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("finding_aids", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("originals_location", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("copies_location", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("related_units", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("publication_notes", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("conservation_notes", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("general_notes", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("rules_conventions", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("description_dates", sa.Text(), nullable=True))
    op.add_column("archive_documents", sa.Column("parent_reference_code", sa.Text(), nullable=True))
    op.add_column("staging_documents", sa.Column(DATE_EXPRESSION, sa.Text(), nullable=True))

    assignments = ", ".join(f"{column} = s.{column}" for column in BACKFILLED)
    op.execute(
        f"UPDATE archive_documents AS a SET {assignments} "
        "FROM staging_documents AS s WHERE s.description_id = a.description_id"
    )


def downgrade() -> None:
    """Drops the columns; every one is an addition, so nothing depends on them."""
    op.drop_column("staging_documents", DATE_EXPRESSION)
    op.drop_column("archive_documents", "parent_reference_code")
    op.drop_column("archive_documents", "description_dates")
    op.drop_column("archive_documents", "rules_conventions")
    op.drop_column("archive_documents", "general_notes")
    op.drop_column("archive_documents", "conservation_notes")
    op.drop_column("archive_documents", "publication_notes")
    op.drop_column("archive_documents", "related_units")
    op.drop_column("archive_documents", "copies_location")
    op.drop_column("archive_documents", "originals_location")
    op.drop_column("archive_documents", "finding_aids")
    op.drop_column("archive_documents", "physical_characteristics")
    op.drop_column("archive_documents", "reproduction_conditions")
    op.drop_column("archive_documents", "arrangement")
    op.drop_column("archive_documents", "accruals")
    op.drop_column("archive_documents", "appraisal_destruction")
    op.drop_column("archive_documents", "dimension_support")
    op.drop_column("archive_documents", "original_url")
    op.drop_column("archive_documents", DATE_EXPRESSION)
