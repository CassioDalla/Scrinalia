"""The database CLI against a real cluster: creation is idempotent, recreation is gated.

Its own scratch database, created and dropped by this file alone — nothing here touches ``test_db``,
the schema the rest of the suite builds and drops, or the developer's own ``DB_NAME``.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from scrinalia.core.database_cli import _drop, _exists, _maintenance, create, database_name, recreate
from testing.conftest import TEST_DATABASE_URL

#: A name a person is unlikely to type, created by nothing but this file.
SCRATCH_DATABASE = "scrinalia_dbcli_scratch"


def _remove(url: URL) -> None:
    """Drops the scratch database, whatever state a failure left it in."""
    with _maintenance(url) as connection:
        if _exists(connection, database_name(url)):
            _drop(connection, database_name(url))


def _marker_table(url: URL) -> None:
    """Leaves something to lose in the scratch database, so a drop is visible afterwards."""
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE marcador (id int)"))
    finally:
        engine.dispose()


def _tables(url: URL) -> int:
    """How many tables the scratch database carries in ``public``."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            ).scalar_one()
    finally:
        engine.dispose()


@pytest.fixture()
def scratch_url() -> Iterator[URL]:
    url = make_url(TEST_DATABASE_URL).set(database=SCRATCH_DATABASE)
    _remove(url)
    yield url
    _remove(url)


def test_create_makes_an_empty_database(scratch_url: URL) -> None:
    assert create(scratch_url) == 0
    assert _tables(scratch_url) == 0


def test_create_is_idempotent(scratch_url: URL) -> None:
    assert create(scratch_url) == 0
    assert create(scratch_url) == 0
    assert _tables(scratch_url) == 0


def test_recreate_without_a_confirmation_leaves_the_database_alone(scratch_url: URL) -> None:
    create(scratch_url)
    _marker_table(scratch_url)

    assert recreate(scratch_url, assume_yes=False, ask=None) == 1
    assert _tables(scratch_url) == 1


def test_recreate_leaves_an_empty_database(scratch_url: URL) -> None:
    create(scratch_url)
    _marker_table(scratch_url)

    assert recreate(scratch_url, assume_yes=True, ask=None) == 0
    assert _tables(scratch_url) == 0


def test_recreate_creates_a_database_that_is_not_there(scratch_url: URL) -> None:
    # Nothing to lose, so no confirmation is owed.
    assert recreate(scratch_url, assume_yes=False, ask=None) == 0
    assert _tables(scratch_url) == 0
