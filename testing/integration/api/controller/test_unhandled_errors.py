"""What reaches the failure ledger, and what must not.

The catch-all handler is the easiest place in the API to get wrong in a way nobody notices: it can
swallow the 404 of an unknown route, turn a business answer into a recorded incident, or print the
exception text of a programming mistake to an unauthenticated client. These tests pin the boundary
of "unexpected", and pin that the row it writes is findable through the request id.
"""

from contextlib import contextmanager

import pytest
from litestar.testing import TestClient
from sqlalchemy import select

from memoria_curitibana.api import handlers
from memoria_curitibana.asgi import create_app
from memoria_curitibana.domains.archive.exceptions import WorkerNotFoundError
from memoria_curitibana.domains.archive.models.operations import ApiError
from memoria_curitibana.domains.archive.repository.api_error_repo import ApiErrorRecorder
from memoria_curitibana.domains.archive.services.worker_operations_service import WorkerOperationsService
from memoria_curitibana.domains.archive.services.worker_run_service import WorkerRunService


@contextmanager
def _shared_session(db):
    """Hands the test's session to the recorder without closing it on the way out."""
    yield db


@pytest.fixture
def client() -> TestClient:
    with TestClient(app=create_app()) as test_client:
        yield test_client  # type: ignore[misc]


@pytest.fixture
def recorder(db_session, monkeypatch) -> ApiErrorRecorder:
    """The real recorder, writing through the test's session so the row is assertable."""
    bound = ApiErrorRecorder(session_factory=lambda: _shared_session(db_session))
    monkeypatch.setattr(handlers, "_api_error_recorder", bound)
    return bound


def test_an_unknown_route_keeps_answering_404(client: TestClient, mocker) -> None:
    """``HTTPException`` has a handler of its own and it has to keep winning over the catch-all."""
    spy = mocker.patch.object(handlers, "_api_error_recorder")

    response = client.get("/api/v1/nao-existe")

    assert response.status_code == 404
    spy.record.assert_not_called()


def test_a_business_answer_is_not_an_incident(client: TestClient, mocker) -> None:
    """A 404 the API owes a client must not be filed as a defect, or the real ones drown."""
    spy = mocker.patch.object(handlers, "_api_error_recorder")
    mocker.patch.object(WorkerRunService, "trigger", side_effect=WorkerNotFoundError("Worker 'x' não existe."))

    response = client.post("/api/v1/system/workers/x/runs", json={})

    assert response.status_code == 404
    assert response.json()["error_code"] == "WorkerNotFoundError"
    spy.record.assert_not_called()


def test_an_unexpected_failure_is_recorded_with_its_request_id(
    client: TestClient, recorder: ApiErrorRecorder, db_session, mocker
) -> None:
    mocker.patch.object(WorkerOperationsService, "list_workers", side_effect=RuntimeError("boom: o serviço explodiu"))

    response = client.get("/api/v1/system/workers", headers={"X-Request-ID": "trace-42"})

    assert response.status_code == 500
    assert response.json()["error_code"] == "InternalError"
    assert response.headers["x-request-id"] == "trace-42"

    row = db_session.scalars(select(ApiError)).one()
    assert row.request_id == "trace-42"
    assert row.method == "GET"
    assert row.path == "/api/v1/system/workers"
    assert row.status_code == 500
    assert row.message == "RuntimeError: boom: o serviço explodiu"
    assert row.error_fingerprint == "runtimeerror: boom: o serviço explodiu"


def test_the_answer_does_not_publish_the_cause(client: TestClient, recorder: ApiErrorRecorder, mocker) -> None:
    """The API is unauthenticated: the traceback is in the log, not in the response body."""
    mocker.patch.object(WorkerOperationsService, "list_workers", side_effect=RuntimeError("senha-do-banco"))

    body = client.get("/api/v1/system/workers").text

    assert "senha-do-banco" not in body
    assert "InternalError" in body
