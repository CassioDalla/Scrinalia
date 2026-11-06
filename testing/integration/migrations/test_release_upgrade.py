"""The upgrade from the previous release meets the rows an installation already has.

CI's ``alembic upgrade head`` runs on the database pytest has just emptied, so it proves the chain is
syntactically valid and nothing about a collection that carries rows. A backfill that assumes a
column has no nulls, or a ``NOT NULL`` added before its ``UPDATE``, passes that and fails on the
first real upgrade.

This test is the other half. It creates a scratch database, applies the committed 1.7.0 fixture
(``testing/data/migrations/1.7.0``) and runs the real Alembic command against it — the path an
installer takes, with the catalogue and application rows already in place.

``data.sql`` carries the rows the migrations seed (the level ladder, the typologies, the macro
categories and the two origin rows), the release's ``alembic_version`` row, and a handful of
application rows in the tables the next data migration has to survive. **A data migration adds the
rows it touches to that file in the same pull request**, and the assertions below grow with it: the
fixture moves with the schema instead of being regenerated once.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError

from scrinalia.core.database_cli import _drop, _exists, _maintenance, create, database_name
from testing.conftest import TEST_DATABASE_URL

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The release the fixture is a snapshot of. A directory name, so the dump's provenance is visible
#: in the path instead of in a comment.
FIXTURE_DIR = REPO_ROOT / "testing" / "data" / "migrations" / "1.7.0"

#: A name nobody types, created and dropped by this file alone. Nothing here touches ``test_db``,
#: whose schema the rest of the suite builds and drops.
SCRATCH_DATABASE = "scrinalia_upgrade_scratch"


def _remove(url: URL) -> None:
    """Drops the scratch database, whatever state a failure left it in."""
    with _maintenance(url) as connection:
        if _exists(connection, database_name(url)):
            _drop(connection, database_name(url))


@pytest.fixture()
def upgrade_url() -> Iterator[URL]:
    url = make_url(TEST_DATABASE_URL).set(database=SCRATCH_DATABASE)
    _remove(url)
    create(url)
    yield url
    _remove(url)


def _dump(path: Path) -> str:
    """The committed SQL, without the psql meta-commands ``pg_dump`` wraps a dump in.

    ``pg_dump`` 15.19 emits ``\\restrict``/``\\unrestrict`` for psql; psycopg2 rejects them. The
    files are committed stripped, and this keeps a freshly regenerated dump from failing on a line
    that is not SQL.
    """
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith(("\\restrict", "\\unrestrict"))
    )


def _restore(url: URL) -> None:
    """Applies the schema and then the rows, in the order an installation builds them."""
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(_dump(FIXTURE_DIR / "schema.sql"))
            connection.exec_driver_sql(_dump(FIXTURE_DIR / "data.sql"))
    finally:
        engine.dispose()


def _revision(url: URL) -> str | None:
    """The Alembic revision the database is at, read from its own ``alembic_version``."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def _head() -> str:
    """The revision this checkout's migration scripts end at."""
    head = ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini"))).get_current_head()
    assert head is not None, "the migration scripts have more than one head, or none"
    return head


def _alembic(url: URL, *args: str) -> subprocess.CompletedProcess[str]:
    """Runs an Alembic command the way the entrypoint does, against the scratch database.

    A subprocess, and not ``alembic.command.upgrade`` in this process: ``migrations/env.py`` reads
    ``settings.DATABASE_URL``, and the suite's process is connected to ``test_db``. Pointing the
    ``DB_*`` variables at the scratch database for the child keeps the two apart without mutating
    the settings every other fixture shares.
    """
    env = {
        **os.environ,
        "DB_HOST": url.host or "localhost",
        "DB_PORT": str(url.port or 5432),
        "DB_USER": url.username or "",
        "DB_PASS": url.password or "",
        "DB_NAME": database_name(url),
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _upgrade(url: URL) -> None:
    """Runs ``alembic upgrade head``, and fails with the migration's own output when it does not."""
    result = _alembic(url, "upgrade", "head")
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"


def test_the_previous_release_upgrades_with_its_rows(upgrade_url: URL) -> None:
    """The 1.7.0 fixture reaches head with the catalogues and the application rows intact."""
    _restore(upgrade_url)
    fixture_version = _revision(upgrade_url)
    assert fixture_version is not None, "the fixture carries no alembic_version row"

    # The child must be looking at the scratch database, not at the suite's: if ``DB_*`` were lost,
    # ``alembic current`` would read ``test_db`` and print no revision at all.
    current = _alembic(upgrade_url, "current")
    assert current.returncode == 0, current.stderr
    assert fixture_version in current.stdout

    _upgrade(upgrade_url)

    assert _revision(upgrade_url) == _head()

    engine = create_engine(upgrade_url)
    try:
        with engine.connect() as connection:
            # The rows the migrations seed are data of an installation, and a migration that
            # rewrites the ladder or the catalogues must keep them consistent.
            assert connection.execute(text("SELECT count(*) FROM archive_description_levels")).scalar_one() == 6
            assert connection.execute(text("SELECT count(*) FROM archive_typologies")).scalar_one() == 10
            assert connection.execute(text("SELECT count(*) FROM archive_macro_categories")).scalar_one() == 8
            origins = connection.execute(text("SELECT code FROM ingestion_origins ORDER BY code")).scalars().all()
            assert origins == ["csv", "manual"]

            # The application rows: a fund, a series and an item, with the materialised path and
            # the review status each one carries.
            documents = connection.execute(
                text(
                    "SELECT description_id, original_title, final_title, review_status, parent_id, path "
                    "FROM archive_documents ORDER BY description_id"
                )
            ).all()
            assert documents == [
                (
                    "fixture-fundo",
                    "Fundo Câmara Municipal",
                    "Câmara Municipal",
                    "PENDING_AI",
                    None,
                    "fundo",
                ),
                (
                    "fixture-item",
                    "Item Ata 1890",
                    "Ata de 1890",
                    "NEEDS_REVIEW",
                    "fixture-serie",
                    "fundo/serie/item",
                ),
                (
                    "fixture-serie",
                    "Série Atas",
                    "Atas da Câmara",
                    "HUMAN_APPROVED",
                    "fixture-fundo",
                    "fundo/serie",
                ),
            ]

            users = connection.execute(text("SELECT email, name, role, locale FROM auth_users ORDER BY user_id")).all()
            assert users == [
                ("admin@example.org", "Ada Curadora", "ADMIN", "pt-BR"),
                ("viewer@example.org", "Bruno Consulta", "VIEWER", "en"),
            ]

            assert connection.execute(text("SELECT name FROM archive_tags ORDER BY tag_id")).scalars().all() == [
                "Saúde",
                "Educação",
                "Urbanismo",
            ]
            assert connection.execute(text("SELECT count(*) FROM archive_document_tags")).scalar_one() == 2
            assert connection.execute(text("SELECT worker_name, status FROM archive_worker_runs")).one() == (
                "ner",
                "SUCCESS",
            )
            assert (
                connection.execute(
                    text("SELECT raw_title FROM raw_data WHERE description_id = 'fixture-item'")
                ).scalar_one()
                == "Ata 1890"
            )

        # The constraints a backfill must not violate: the locale is the check the head migration
        # added, and the parent is the hierarchy's own foreign key.
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO auth_users (email, name, password_hash, role, locale) "
                    "VALUES ('bad-locale@example.org', 'Bad Locale', 'hash', 'VIEWER', 'xx')"
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO archive_documents "
                    "(description_id, original_title, staging_content_hash, execution_log, "
                    "review_status, is_anomaly, path, parent_id) "
                    "VALUES ('orphan', 'Orphan', repeat('d', 64), '{}', 'PENDING_AI', false, "
                    "'orphan', 'no-such-parent')"
                )
            )
    finally:
        engine.dispose()
