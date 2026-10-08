"""The orchestrator's two questions must stay apart.

A liveness probe that consults the database restarts the API whenever the database restarts, and a
readiness probe that never consults it keeps sending traffic to an instance that cannot answer.
These tests pin both directions, that the probe talks to nothing else, and that the unauthenticated
route never prints *why* it failed.
"""

from collections.abc import Iterator

import pytest
import requests
from litestar.testing import TestClient

from scrinalia.api import health_probe
from scrinalia.asgi import create_app


class _Connection:
    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def execute(self, statement: object) -> None:
        return None


class _Engine:
    def connect(self) -> _Connection:
        return _Connection()


def _engine_that_answers() -> _Engine:
    return _Engine()


def _engine_that_refuses() -> _Engine:
    raise RuntimeError("could not connect to server: Connection refused (localhost:5432)")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app=create_app()) as test_client:
        yield test_client


def test_liveness_answers_while_the_database_is_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_probe, "_probe_engine", _engine_that_refuses)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_readiness_answers_503_when_the_database_is_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_probe, "_probe_engine", _engine_that_refuses)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    # Why it failed belongs in the log: the route is unauthenticated, and a connection error
    # stringifies host and port.
    assert "5432" not in response.text


def test_readiness_answers_200_when_the_database_answers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_probe, "_probe_engine", _engine_that_answers)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_readiness_never_calls_anything_but_the_database(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama and object storage are the panel's business; a probe must not pay for them."""
    monkeypatch.setattr(health_probe, "_probe_engine", _engine_that_answers)

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("o probe de orquestrador não pode falar com outro serviço")

    monkeypatch.setattr(requests, "get", explode)

    assert client.get("/health/ready").status_code == 200


def test_the_orchestrator_routes_stay_out_of_the_contract() -> None:
    paths = create_app().openapi_schema.to_schema()["paths"]  # type: ignore[union-attr]

    assert [path for path in paths if path.startswith("/health")] == []
