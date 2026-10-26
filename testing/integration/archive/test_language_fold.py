"""The migration's SQL fold is the catalogue's Python fold, asserted where it runs (#203).

The data migration duplicates the fold on purpose — replaying history must reproduce the state it
produced, not today's implementation — so the two are pinned against each other here. The spellings
are the ones the reference collection really declares (``Português Brasil`` 78 times,
``Português/Brasil`` 22 times) plus the variants a source produces.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import text

from scrinalia.domains.archive.domain.language_catalog import normalize_language
from scrinalia.domains.staging.models import StagingDocument

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations" / "versions"
_MIGRATION_FILE = "6c46426b048a_fold_the_language_spelling.py"

SPELLINGS = (
    "Português Brasil",
    "Português/Brasil",
    "PORTUGUÊS BRASIL",
    "portugues brasil",
    "Português",
    "  portugues  ",
    "Inglês",
    "PT-BR",
    "Port.",
)


def _migration() -> ModuleType:
    """The migration module, by path: ``migrations`` is deliberately not an importable package."""
    spec = importlib.util.spec_from_file_location(
        _MIGRATION_FILE.removesuffix(".py"), _MIGRATIONS_DIR / _MIGRATION_FILE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_the_sql_fold_and_the_python_fold_agree(db_session, use_test_db, spelling: str) -> None:
    """
    ``SELECT <fold('spelling')>`` must equal ``normalize_language(spelling)``.

    This is the half the unit test cannot see: the Python fold could be right and the SQL one wrong
    (an accent the wrapper does not strip, an NBSP ``\\s`` does not cover), and the migration would
    silently miss rows.
    """
    migration = _migration()
    sql = migration._fold(migration._literal(spelling))

    assert db_session.scalar(text(f"SELECT {sql}")) == normalize_language(spelling)


def test_the_statements_fold_the_spellings_the_collection_declares(db_session, use_test_db) -> None:
    """
    The whole statement, over rows: the measured variants become ``Português`` and the unknown
    language keeps the source's text.
    """
    declared = {
        "lang-fold-1": "Português Brasil",
        "lang-fold-2": "Português/Brasil",
        "lang-fold-3": "portugues",
        "lang-fold-4": "Linguagem Inventada",
    }
    for description_id, language in declared.items():
        db_session.add(
            StagingDocument(
                description_id=description_id,
                title="Registro",
                raw_content_hash=f"hash-{description_id}",
                language_name=language,
            )
        )
    db_session.commit()

    migration = _migration()
    for _table, statement in migration.FOLD_STATEMENTS:
        db_session.execute(text(statement))
    db_session.commit()

    db_session.expire_all()
    for description_id, language in declared.items():
        folded = db_session.get(StagingDocument, description_id)
        assert folded is not None
        expected = "Português" if language.startswith(("Português", "portugues")) else language
        assert folded.language_name == expected, f"{language!r} virou {folded.language_name!r}"
