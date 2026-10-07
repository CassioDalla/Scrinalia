"""The HTTP shape of the failures read, and the filter that leads back to the occurrences.

The service tests own the grouping; here what is pinned is the contract a client sees — the envelope,
the source vocabulary, and that ``/system/runs?fingerprint=`` really narrows the ledger instead of
ignoring the parameter and answering everything.
"""

import pytest
from litestar.testing import TestClient

from memoria_curitibana.asgi import create_app
from memoria_curitibana.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from memoria_curitibana.domains.archive.models.operations import ApiError
from memoria_curitibana.domains.archive.repository.worker_run_repo import WorkerRunRepository


@pytest.fixture
def client(api_uses_test_db) -> TestClient:
    with TestClient(app=create_app()) as test_client:
        yield test_client  # type: ignore[misc]


def _failed_run(db, *, worker: str = "ner", message: str = "boom") -> int:
    repo = WorkerRunRepository(db)
    run = repo.create_running(
        worker,
        trigger=WorkerRunTrigger.CLI,
        requested_by=None,
        engine_name=None,
        preset=None,
        config={},
    )
    repo.finish(run.run_id, status=WorkerRunStatus.FAILED, error=message, error_kind="RuntimeError")
    return run.run_id


def test_the_failures_route_answers_the_grouped_envelope(client: TestClient, db_session) -> None:
    _failed_run(db_session, message="boom")
    db_session.add(
        ApiError(
            request_id="trace-42", method="GET", path="/api/v1/documents", status_code=500, message="RuntimeError: boom"
        )
    )
    db_session.flush()

    response = client.get("/api/v1/system/failures")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    group = body["items"][0]
    assert group["fingerprint"] == "runtimeerror: boom"
    assert group["occurrences"] == 2
    assert sorted(group["sources"]) == ["API", "WORKER"]
    assert group["worker_names"] == ["ner"]
    assert group["last_path"] == "/api/v1/documents"
    assert group["last_request_id"] == "trace-42"
    assert group["first_seen"] and group["last_seen"]


def test_the_runs_route_filters_by_fingerprint(client: TestClient, db_session) -> None:
    _failed_run(db_session, message="boom")
    _failed_run(db_session, message="outra coisa")

    response = client.get("/api/v1/system/runs", params={"fingerprint": "runtimeerror: boom"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["error_fingerprint"] == "runtimeerror: boom"
    assert body["items"][0]["error"] == "RuntimeError: boom"


def test_a_fingerprint_that_matches_nothing_answers_an_empty_page(client: TestClient, db_session) -> None:
    _failed_run(db_session, message="boom")

    body = client.get("/api/v1/system/runs", params={"fingerprint": "nao-existe"}).json()

    assert body["total"] == 0
    assert body["items"] == []
