"""link the descriptions to the level catalog

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5b6
Create Date: 2026-10-04 21:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1f2c3d4e5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Accent-, case- and punctuation-insensitive fold of a level spelling, in SQL.
#:
#: It mirrors ``domain.level_catalog.normalize_level_name`` and exists here so the migration
#: stays self-contained instead of importing application code (which would make replaying
#: history depend on today's implementation). The two are pinned together by a test over the
#: four spellings the real collection declares plus their realistic variants.
#:
#: Details that are easy to get wrong and are deliberate:
#:   * ``immutable_unaccent`` is the same wrapper the full-text search uses, so there is one
#:     accent implementation in the database, not two;
#:   * ``chr(160)`` (NBSP) is replaced explicitly because ``\s`` in PostgreSQL does **not**
#:     cover it, while ``\s`` in Python does — the text-quality work hit the same trap;
#:   * the separator class is ``/``, ``\``, en dash, em dash and hyphen, matching ``_SEPARATORS``.
_FOLD_TEMPLATE = (
    "btrim(regexp_replace(regexp_replace(replace(lower(public.immutable_unaccent({column})), "
    "chr(160), ' '), '[/\\\\——-]+', ' ', 'g'), '\\s+', ' ', 'g'))"
)


def _fold(column: str) -> str:
    """Builds the fold expression for a column or SQL expression."""
    return _FOLD_TEMPLATE.format(column=column)


def upgrade() -> None:
    """
    Adds the level foreign key and backfills it from the free text, keeping the text column.

    Two stages on purpose: the roadmap is explicit that a wrong de-para here is destructive,
    so this revision only *adds* and *populates*. The text column survives until the result is
    verified, and ``c3d4e5f6a7b8`` is the revision that drops it — and refuses to, while any
    declared level remains unmapped.

    The match prefers the canonical ``name`` over the ``aliases``; only the rows the name does
    not resolve fall through to the alias pass, so the outcome cannot depend on the order rows
    happen to come back in.
    """
    op.add_column("archive_documents", sa.Column("level_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_archive_documents_level_id",
        "archive_documents",
        "archive_description_levels",
        ["level_id"],
        ["level_id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_archive_documents_level_id", "archive_documents", ["level_id"], unique=False)

    connection = op.get_bind()

    connection.execute(
        sa.text(
            f"""
            UPDATE archive_documents AS d
               SET level_id = m.level_id
              FROM archive_description_levels AS m
             WHERE d.level IS NOT NULL
               AND {_fold("d.level")} = {_fold("m.name")}
            """
        )
    )

    connection.execute(
        sa.text(
            f"""
            UPDATE archive_documents AS d
               SET level_id = m.level_id
              FROM archive_description_levels AS m
             WHERE d.level IS NOT NULL
               AND d.level_id IS NULL
               AND {_fold("d.level")} = ANY (
                     SELECT {_fold("spelling")}
                       FROM unnest(m.aliases) AS spelling
               )
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema: the free text is still there, so nothing has to be rebuilt."""
    op.drop_index("ix_archive_documents_level_id", table_name="archive_documents")
    op.drop_constraint("fk_archive_documents_level_id", "archive_documents", type_="foreignkey")
    op.drop_column("archive_documents", "level_id")
