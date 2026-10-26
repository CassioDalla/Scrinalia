"""The runner's DSN is its own, and the application DSN carries the transport.

ADR 0014 lets the external runner authenticate with a least-privilege role and its own TLS
parameters without the API's credential. The two decisions that make that possible are one
property and one function, so they are pinned here: ``DATABASE_URL`` appends ``DB_SSLMODE``, and
``runner_database_url`` prefers ``RUNNER_DATABASE_URL`` and falls back to the application DSN.
"""

from pydantic import SecretStr

from scrinalia.core import database
from scrinalia.core.config import settings


def test_the_application_dsn_carries_the_ssl_mode(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DB_SSLMODE", "verify-full")

    assert settings.DATABASE_URL.endswith("?sslmode=verify-full")


def test_the_runner_falls_back_to_the_application_dsn(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RUNNER_DATABASE_URL", None)

    assert database.runner_database_url() == settings.DATABASE_URL


def test_the_runner_uses_its_own_dsn_when_configured(monkeypatch) -> None:
    own = "postgresql+psycopg2://scrinalia_runner:secret@db.example.org:5432/scrinalia?sslmode=verify-full"
    monkeypatch.setattr(settings, "RUNNER_DATABASE_URL", SecretStr(own))

    assert database.runner_database_url() == own
