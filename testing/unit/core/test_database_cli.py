"""The database CLI's decision points: which URL it acts on, and who may destroy a database.

Both operations are covered against a real cluster by
``testing/integration/core/test_database_cli.py``; these are the parts that have to be right even
when no database answers, and none of them opens a connection.
"""

import pytest
from sqlalchemy.engine import make_url

from scrinalia.core.config import settings
from scrinalia.core.database_cli import (
    MAINTENANCE_DATABASE,
    Prompt,
    _confirmed,
    database_name,
    maintenance_url,
)


def test_maintenance_url_changes_only_the_database() -> None:
    url = make_url(settings.DATABASE_URL)
    maintenance = maintenance_url(url)

    assert maintenance.database == MAINTENANCE_DATABASE
    assert (maintenance.host, maintenance.port) == (url.host, url.port)
    assert (maintenance.username, maintenance.password) == (url.username, url.password)


def test_a_url_without_a_database_is_refused() -> None:
    # The shape an empty ``DB_NAME`` produces: ``DATABASE_URL`` interpolates it after a slash, so
    # the path is empty and SQLAlchemy reads the database as ``""``.
    url = make_url("postgresql://admin:admin123@localhost:5432/")

    with pytest.raises(ValueError, match="DB_NAME"):
        database_name(url)


def _typing(answer: str) -> Prompt:
    """A prompt a test can answer, in place of ``input``."""

    def answer_with(_: str) -> str:
        return answer

    return answer_with


def test_the_name_typed_back_is_the_confirmation() -> None:
    assert _confirmed("scrinalia_zeroed", assume_yes=False, ask=_typing("scrinalia_zeroed")) is True
    assert _confirmed("scrinalia_zeroed", assume_yes=False, ask=_typing(" scrinalia_zeroed\n")) is True


def test_anything_else_at_the_prompt_refuses() -> None:
    assert _confirmed("scrinalia_zeroed", assume_yes=False, ask=_typing("outra")) is False
    assert _confirmed("scrinalia_zeroed", assume_yes=False, ask=_typing("")) is False


def test_without_a_prompt_the_drop_is_refused() -> None:
    assert _confirmed("scrinalia_zeroed", assume_yes=False, ask=None) is False


def test_an_explicit_yes_skips_the_prompt() -> None:
    assert _confirmed("scrinalia_zeroed", assume_yes=True, ask=None) is True
