"""HTTP contract of the operations panel: the envelopes and the error codes.

The numbers themselves are covered against the database in the service tests; here the services are
mocked and what is pinned is the shape a client sees — including that a worker already running
answers 409 and a bad override answers 422, not a 500.
"""

from datetime import UTC, datetime

from litestar.testing import TestClient

from scrinalia.domains.archive.exceptions import (
    InvalidWorkerSettingsError,
    WorkerNotFoundError,
    WorkerRunAlreadyActiveError,
)
from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.schemas.system_schema import (
    DatabaseHealthDTO,
    OllamaHealthDTO,
    ProcessHealthDTO,
    StorageHealthDTO,
    SystemHealthResponse,
    SystemWorkerSettingsResponse,
    SystemWorkersResponse,
    WorkerRunDTO,
    WorkerRunListResponse,
    WorkerSettingsDTO,
    WorkerSettingsItemDTO,
    WorkerSettingsRevisionListResponse,
    WorkerStatusDTO,
)
from scrinalia.domains.archive.services.worker_operations_service import WorkerOperationsService
from scrinalia.domains.archive.services.worker_run_service import WorkerRunService


def _settings() -> WorkerSettingsDTO:
    return WorkerSettingsDTO(
        worker_name="ner",
        engine_name="spacy_ner",
        preset="gpu",
        db_batch_size=64,
        options={},
        overridden=False,
        engine_source="signature",
        config={"model": "pt_core_news_lg", "device": "gpu"},
        available_engines=[],
    )


def _status() -> WorkerStatusDTO:
    return WorkerStatusDTO(
        name="ner",
        label="Extração de entidades (NER)",
        description="d",
        order=2,
        unit="document",
        governed=True,
        settings=_settings(),
        pending=10,
        processed=0,
        failed=0,
    )


def _run() -> WorkerRunDTO:
    return WorkerRunDTO(
        run_id=1,
        worker_name="ner",
        status=WorkerRunStatus.QUEUED,
        trigger=WorkerRunTrigger.API,
        queued_at=datetime.now(UTC),
    )


def test_the_panel_lists_every_worker(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(WorkerOperationsService, "list_workers")
    mock.return_value = SystemWorkersResponse(workers=[_status()], generated_at=datetime.now(UTC))

    response = client.get("/api/v1/system/workers")

    assert response.status_code == 200
    body = response.json()
    assert body["workers"][0]["name"] == "ner"
    assert body["workers"][0]["settings"]["config"]["model"] == "pt_core_news_lg"
    assert body["workers"][0]["pending"] == 10
    assert body["generated_at"]


def test_the_settings_read_carries_the_configuration_and_no_queue(client: TestClient, mocker) -> None:
    """The configuration screen has its own read, and the panel's counters stay out of it.

    The ``pending`` assertion is the split's own: the two screens answer different questions, and a
    configuration read that started carrying queue numbers would be paying for the staging scan the
    panel pays for.
    """
    mock = mocker.patch.object(WorkerOperationsService, "list_settings")
    mock.return_value = SystemWorkerSettingsResponse(
        workers=[
            WorkerSettingsItemDTO(
                name="ner",
                label="Extração de entidades (NER)",
                description="d",
                order=2,
                settings=_settings(),
            )
        ],
        generated_at=datetime.now(UTC),
    )

    response = client.get("/api/v1/system/workers/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["workers"][0]["label"] == "Extração de entidades (NER)"
    assert body["workers"][0]["settings"]["preset"] == "gpu"
    assert "pending" not in body["workers"][0]
    assert body["generated_at"]


def test_a_worker_already_running_answers_conflict(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(WorkerRunService, "trigger")
    mock.side_effect = WorkerRunAlreadyActiveError("Já existe uma execução em andamento para o worker 'ner'.")

    response = client.post("/api/v1/system/workers/ner/runs", json={})

    assert response.status_code == 409
    assert response.json()["error_code"] == "WorkerRunAlreadyActiveError"


def test_an_unknown_worker_answers_not_found(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(WorkerRunService, "trigger")
    mock.side_effect = WorkerNotFoundError("Worker 'nao-existe' não existe.")

    assert client.post("/api/v1/system/workers/nao-existe/runs", json={}).status_code == 404


def test_an_invalid_override_answers_unprocessable(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(WorkerOperationsService, "update_settings")
    mock.side_effect = InvalidWorkerSettingsError("Engine 'x' não existe para o eixo NER.")

    response = client.put("/api/v1/system/workers/ner/settings", json={"engine_name": "x"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "InvalidWorkerSettingsError"


def test_the_trigger_answers_the_queued_run(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(WorkerRunService, "trigger")
    mock.return_value = _run()

    response = client.post("/api/v1/system/workers/ner/runs", json={"requested_by": "teste"})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["trigger"] == "API"
    assert body["run_id"] == 1


def test_the_ledger_pages_and_echoes_the_window(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(WorkerRunService, "list_runs")
    mock.return_value = WorkerRunListResponse(items=[_run()], total=1, limit=20, offset=0)

    body = client.get("/api/v1/system/runs", params={"worker": "ner", "limit": 20}).json()

    assert body["total"] == 1
    assert body["items"][0]["worker_name"] == "ner"
    mock.assert_called_once()
    assert mock.call_args.kwargs["worker_name"] == "ner"


def test_the_settings_round_trip_through_the_http_layer(client: TestClient, mocker) -> None:
    update = mocker.patch.object(WorkerOperationsService, "update_settings")
    update.return_value = _settings()
    clear = mocker.patch.object(WorkerOperationsService, "clear_settings")
    clear.return_value = _settings()
    revisions = mocker.patch.object(WorkerOperationsService, "list_revisions")
    revisions.return_value = WorkerSettingsRevisionListResponse(items=[], total=0)

    assert client.put("/api/v1/system/workers/ner/settings", json={"preset": "gpu"}).status_code == 200
    assert client.delete("/api/v1/system/workers/ner/settings").status_code == 200
    assert client.get("/api/v1/system/workers/ner/settings/revisions").json()["total"] == 0


def test_the_health_endpoint_answers_every_probe(client: TestClient, mocker) -> None:
    mocker.patch(
        "scrinalia.api.controllers.system_controller.probe_infrastructure",
        return_value=SystemHealthResponse(
            generated_at=datetime.now(UTC),
            database=DatabaseHealthDTO(ok=True, documents=10),
            ollama=OllamaHealthDTO(ok=True, host="http://localhost:11434", host_source="default"),
            storage=StorageHealthDTO(configured=False, ok=False),
            process=ProcessHealthDTO(
                log_level="INFO",
                debug=False,
                log_dir="logs",
                database="localhost:5432/db",
                public_scrape_configured=False,
            ),
        ),
    )

    body = client.get("/api/v1/system/health").json()

    assert body["database"]["documents"] == 10
    assert body["ollama"]["host_source"] == "default"
    assert body["storage"]["configured"] is False
    assert body["process"]["secrets_present"] == {}
