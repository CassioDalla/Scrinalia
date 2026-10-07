"""Every request leaves with an id, and every log line of that request carries it.

The id is what makes a failure report findable: without it, "quebrou às 14:32" is a time range to
read by eye, and the record of the 500 sits in a rotated file next to a thousand other lines. The
tests here pin the three properties that make it trustworthy — the client's id is honoured, a forged
one is refused, and the id reaches a record emitted from inside a threaded handler, which is where
all the work actually happens.
"""

import pytest
from litestar import Litestar, get
from litestar.testing import TestClient

from scrinalia.api.middleware import MAX_REQUEST_ID_LENGTH, RequestContextMiddleware
from scrinalia.asgi import create_app
from scrinalia.core.logger import logger


@get("/work", sync_to_thread=True)
def _work() -> dict[str, bool]:
    """A handler that logs, in a thread — exactly like every route of this API."""
    logger.info("trabalho feito")
    return {"ok": True}


@pytest.fixture
def records() -> list[dict]:
    """Captures the loguru records emitted during a test, and detaches the sink afterwards."""
    captured: list[dict] = []

    def sink(message) -> None:  # type: ignore[no-untyped-def]
        captured.append({**message.record["extra"], "message": message.record["message"]})

    handler_id = logger.add(sink, level="INFO", format="{message}")
    try:
        yield captured
    finally:
        logger.remove(handler_id)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app=Litestar(route_handlers=[_work], middleware=[RequestContextMiddleware()])) as test_client:
        yield test_client  # type: ignore[misc]


def test_the_client_id_is_echoed_back(client: TestClient) -> None:
    response = client.get("/work", headers={"X-Request-ID": "trace-42"})

    assert response.headers["x-request-id"] == "trace-42"


def test_a_missing_id_is_generated(client: TestClient) -> None:
    generated = client.get("/work").headers["x-request-id"]

    assert generated
    assert generated != client.get("/work").headers["x-request-id"]


@pytest.mark.parametrize("forged", ["id com espaco; e ponto e virgula", "x" * (MAX_REQUEST_ID_LENGTH + 1)])
def test_a_forged_id_is_replaced_instead_of_echoed(client: TestClient, forged: str) -> None:
    """The value is written into a header and into a log line: it is accepted only if it is an id."""
    echoed = client.get("/work", headers={"X-Request-ID": forged}).headers["x-request-id"]

    assert echoed != forged


def test_the_request_id_reaches_a_record_from_inside_the_handler(client: TestClient, records: list[dict]) -> None:
    client.get("/work", headers={"X-Request-ID": "trace-42"})

    inside = [record for record in records if record["message"] == "trabalho feito"]
    assert inside, "o handler não registrou nada"
    assert inside[0]["request_id"] == "trace-42"


def test_the_access_line_carries_the_status_and_the_id(client: TestClient, records: list[dict]) -> None:
    client.get("/work", headers={"X-Request-ID": "trace-42"})

    access = [record for record in records if "GET /work ->" in record["message"]]
    assert access, "nenhuma linha de acesso foi emitida"
    assert access[0]["request_id"] == "trace-42"
    assert "-> 200" in access[0]["message"]


def test_the_orchestrator_probes_are_quiet_in_the_access_log(records: list[dict]) -> None:
    """An orchestrator asks every few seconds; logging each probe would rotate the file for nothing."""
    with TestClient(app=create_app()) as app_client:
        assert app_client.get("/health/live").status_code == 200

    # The filter is the access line's own shape: httpx logs the URL of its request, and that record
    # is about the client, not about what this application decided to write.
    assert [record for record in records if "GET /health/live ->" in record["message"]] == []
