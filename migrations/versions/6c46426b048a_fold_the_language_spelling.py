"""fold the language spelling

Revision ID: 6c46426b048a
Revises: e3084fbf75ba
Create Date: 2026-10-26 13:01:14.946299

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c46426b048a"
down_revision: str | Sequence[str] | None = "e3084fbf75ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The catalogue as this revision understood it: ``(canonical name, aliases)``. It duplicates
#: ``domains.archive.domain.language_catalog`` on purpose — replaying history must reproduce the
#: state it produced, not today's catalogue — and the duplication is pinned by a test instead of
#: trusted (``testing/unit/archive/domain/test_language_catalog.py``).
LANGUAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Português", ("Português Brasil", "Português/Brasil", "Português do Brasil", "PT-BR", "PT", "Port.")),
    ("Inglês", ("English", "Ing.")),
    ("Espanhol", ("Castelhano", "Español", "Esp.")),
    ("Francês", ("Français",)),
    ("Alemão", ("Deutsch", "German")),
    ("Latim", ("Latin",)),
    ("Grego", ("Greek",)),
    ("Hebraico", ("Hebrew",)),
    ("Holandês", ("Dutch", "Neerlandês")),
    ("Húngaro", ("Hungarian",)),
    ("Iídiche", ("Yiddish",)),
    ("Japonês", ("Japanese",)),
    ("Chinês", ("Chinese",)),
    ("Coreano", ("Korean",)),
    ("Norueguês", ("Norwegian",)),
    ("Polonês", ("Polish", "Polaco")),
    ("Romeno", ("Romanian",)),
    ("Russo", ("Russian",)),
    ("Sueco", ("Swedish",)),
    ("Tcheco", ("Czech", "Checo")),
    ("Turco", ("Turkish",)),
    ("Ucraniano", ("Ukrainian",)),
    ("Árabe", ("Arabic", "Arabe")),
    # No variant is known for these, but listing them still normalizes a source that writes the name
    # in another case or without its accent ("italiano" -> "Italiano").
    ("Guarani", ()),
    ("Italiano", ()),
    ("Nheengatu", ()),
)

#: Accent-, case- and punctuation-insensitive fold of a language spelling, in SQL.
#:
#: It mirrors ``language_catalog.normalize_language`` and exists here so the migration stays
#: self-contained instead of importing application code (which would make replaying history depend on
#: today's implementation). Deliberate details, the same ones the level fold pins:
#:
#: * ``immutable_unaccent`` is the wrapper the full-text search uses, so the database has one accent
#:   implementation and not two;
#: * ``chr(160)`` (NBSP) is replaced explicitly because ``\s`` in PostgreSQL does not cover it while
#:   ``\s`` in Python does;
#: * the separator class is ``/``, ``\``, en dash, em dash and hyphen, matching ``_SEPARATORS``.
_FOLD_TEMPLATE = (
    "btrim(regexp_replace(regexp_replace(replace(lower(public.immutable_unaccent({column})), "
    "chr(160), ' '), '[/\\\\——-]+', ' ', 'g'), '\\s+', ' ', 'g'))"
)


def _fold(column: str) -> str:
    """Builds the fold expression for a column or SQL expression."""
    return _FOLD_TEMPLATE.format(column=column)


def _literal(value: str) -> str:
    """A SQL string literal, quoted the way PostgreSQL expects."""
    return "'" + value.replace("'", "''") + "'"


def _spelling_values() -> str:
    """The ``(folded spelling, canonical name)`` table every statement joins against."""
    rows: list[str] = []
    for canonical, aliases in LANGUAGES:
        for spelling in (canonical, *aliases):
            rows.append(f"({_fold(_literal(spelling))}, {_literal(canonical)})")
    return ",\n        ".join(rows)


def _statement(table: str) -> str:
    """
    One table's fold, as a single UPDATE joined against the catalogue's spellings.

    A value the catalogue does not know is left untouched: the archive keeps the source's text, and
    the dossier marks it as outside the catalogue instead of being given a guess.
    """
    return (
        f"UPDATE {table} AS d\n"
        "   SET language_name = m.canonical\n"
        f"  FROM (VALUES\n        {_spelling_values()}\n      ) AS m(folded, canonical)\n"
        " WHERE d.language_name IS NOT NULL\n"
        f"   AND {_fold('d.language_name')} = m.folded"
    )


#: The statements the upgrade runs, one per table. Exposed for the test that pins this SQL to the
#: Python fold by running it over scratch rows.
FOLD_STATEMENTS: tuple[tuple[str, str], ...] = (
    ("staging_documents", _statement("staging_documents")),
    ("archive_documents", _statement("archive_documents")),
)


def upgrade() -> None:
    """
    Folds every declared language spelling to the catalogue's name, in both layers.

    Measured before this revision: the reference collection declares ``Português Brasil`` in 78
    descriptions and ``Português/Brasil`` in 22 — two spellings of one language, both rendered as
    unknown by a dossier that compares strings. The transfer canonicalizes from now on, so this
    revision is the one-off for what was written before it.

    It is idempotent: a canonical name folds to itself, so a second run matches and writes the same
    value. A spelling the catalogue does not know is deliberately left alone.
    """
    connection = op.get_bind()
    for table, statement in FOLD_STATEMENTS:
        result = connection.execute(sa.text(statement))
        if result.rowcount:
            print(f"folded {result.rowcount} language spelling(s) in {table}")


def downgrade() -> None:
    """
    Nothing to undo, and this is not an oversight.

    The fold is lossy: ``Português Brasil`` and ``Português/Brasil`` both became ``Português``, and
    which one a row declared is no longer recorded in the column (it remains in ``raw_data.payload``
    for the ingestions that carried it). A downgrade that guessed would be inventing data.
    """
