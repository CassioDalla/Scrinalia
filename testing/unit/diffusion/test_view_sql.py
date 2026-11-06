"""The current view definitions are definitions a migration actually ran (ADR 0023).

A view has no ``alembic check`` twin: unlike a table, nothing compares the database with the model,
so a change to ``coverage.py`` without a migration would make a fresh install and an upgraded one
disagree in silence. The suite builds its schema from the current constant, so it would keep passing
against a predicate production does not have.

The gate is the pair: ``coverage.py`` holds the definition the code reads **today**, and at least one
migration must carry the exact same statement — the one that put it in the databases. A change
without a migration fails here, and so does a migration that changes the view away from the constant.
"""

from __future__ import annotations

from importlib import util
from pathlib import Path

from scrinalia.domains.diffusion import coverage

VERSIONS = Path(__file__).resolve().parents[3] / "migrations" / "versions"


def _normalized(sql: str) -> str:
    """The statement without the indentation that only makes the file readable."""
    return " ".join(sql.split())


def _migration_statements(constant: str) -> set[str]:
    """Every value of ``constant`` a migration module defines, normalized."""
    found: set[str] = set()
    for path in sorted(VERSIONS.glob("*.py")):
        spec = util.spec_from_file_location(f"migration_{path.stem}", path)
        assert spec is not None and spec.loader is not None, f"{path} is not importable"
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        value = getattr(module, constant, None)
        if isinstance(value, str):
            found.add(_normalized(value))
    return found


def test_the_coverage_view_is_one_a_migration_ran() -> None:
    statements = _migration_statements("COVERAGE_VIEW_SQL")
    assert _normalized(coverage.CREATE_COVERAGE_VIEW_SQL) in statements, (
        "coverage.CREATE_COVERAGE_VIEW_SQL is not the definition of any migration. A view change "
        "needs a migration that runs the new statement; the test schema and the migration would "
        "otherwise describe different predicates."
    )


def test_the_exclusions_view_is_one_a_migration_ran() -> None:
    statements = _migration_statements("EXCLUSIONS_VIEW_SQL")
    assert _normalized(coverage.CREATE_EXCLUSIONS_VIEW_SQL) in statements, (
        "coverage.CREATE_EXCLUSIONS_VIEW_SQL is not the definition of any migration. A view change "
        "needs a migration that runs the new statement."
    )
