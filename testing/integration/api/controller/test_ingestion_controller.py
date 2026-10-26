"""HTTP contract of the ingestion surface: the origin panel and the manual entry.

The numbers and the writes are covered against the database in ``test_origin_service.py``; here the
services are mocked and what is pinned is the envelope: the list carries the origin's own queue, the
manual submit answers 201 with its code and the record, and the three operator writes keep their
permissions (the route-access gate walks the built app, so a missing declaration fails there).
"""

from datetime import UTC, datetime

from litestar.testing import TestClient

from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.schemas.responses import RouteMessageCode
from scrinalia.domains.archive.schemas.system_schema import WorkerRunDTO
from scrinalia.domains.ingestion.csv_import import CsvRowStatus
from scrinalia.domains.ingestion.exceptions import CsvImportLimitError
from scrinalia.domains.ingestion.schemas import (
    CsvImportResponse,
    CsvImportResultDTO,
    CsvRowResultDTO,
    IngestionOriginDTO,
    IngestionOriginListResponse,
    ManualIngestionResponse,
    ManualIngestionResultDTO,
)
from scrinalia.domains.ingestion.service import IngestionOriginService


def _origin() -> IngestionOriginDTO:
    return IngestionOriginDTO(
        code="manual",
        label="Entrada manual",
        description="Um registro digitado.",
        kind="MANUAL",
        enabled=True,
        config={},
        config_fields=[],
        options={},
        option_fields=[],
        schedule=None,
        pending=3,
        processed=2,
        failed=0,
        last_run_id=7,
        last_run_status=WorkerRunStatus.SUCCESS,
        last_run_at=datetime.now(UTC),
        runner_available=True,
    )


def _run() -> WorkerRunDTO:
    return WorkerRunDTO(
        run_id=9,
        worker_name="ingestion",
        origin_code="pmc",
        status=WorkerRunStatus.QUEUED,
        trigger=WorkerRunTrigger.API,
        queued_at=datetime.now(UTC),
    )


def test_the_origin_list_carries_its_own_queue(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(IngestionOriginService, "list_origins")
    mock.return_value = IngestionOriginListResponse(origins=[_origin()], generated_at=datetime.now(UTC))

    response = client.get("/api/v1/ingestion/origins")

    assert response.status_code == 200
    body = response.json()
    assert body["origins"][0]["code"] == "manual"
    assert body["origins"][0]["pending"] == 3
    assert body["origins"][0]["kind"] == "MANUAL"


def test_the_manual_submit_answers_201_with_the_record_and_its_code(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(IngestionOriginService, "create_manual")
    mock.return_value = ManualIngestionResponse(
        code=RouteMessageCode.MANUAL_INGESTION_QUEUED,
        message="Descrição recebida e estruturada.",
        data=ManualIngestionResultDTO(
            description_id="manual-1",
            origin_code="manual",
            staging_saved=True,
            transfer_run_id=11,
            transfer_queued=True,
        ),
    )

    response = client.post("/api/v1/ingestion/manual", json={"title": "Ofício"})

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "MANUAL_INGESTION_QUEUED"
    assert body["data"]["description_id"] == "manual-1"
    assert body["data"]["transfer_queued"] is True
    assert body["data"]["review_status"] == "PENDING_AI"
    mock.assert_called_once()


def test_the_origin_run_is_enqueued_from_the_origin_route(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(IngestionOriginService, "trigger")
    mock.return_value = _run()

    response = client.post("/api/v1/ingestion/origins/pmc/runs", json={})

    assert response.status_code == 201
    assert response.json()["origin_code"] == "pmc"
    mock.assert_called_once()


def test_the_origin_configuration_is_a_patch(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(IngestionOriginService, "update_origin")
    mock.return_value = _origin()

    response = client.patch(
        "/api/v1/ingestion/origins/manual",
        json={"enabled": True, "config": {}, "options": {}},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "manual"
    mock.assert_called_once()


# ==========================================
# THE CSV IMPORT (#191)
# ==========================================


def test_the_csv_spec_publishes_the_map_and_the_bounds(client: TestClient) -> None:
    response = client.get("/api/v1/ingestion/csv/spec")

    assert response.status_code == 200
    body = response.json()
    assert body["origin_code"] == "csv"
    assert body["id"]["label"] == "Identificador"
    assert body["fields"][0]["label"] == "Título"
    assert body["fields"][0]["required"] is True
    assert body["max_rows"] > 0 and body["max_bytes"] > 0


def test_the_csv_import_answers_200_with_the_per_row_report(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(IngestionOriginService, "import_csv")
    mock.return_value = CsvImportResponse(
        code=RouteMessageCode.CSV_IMPORT_QUEUED,
        message="2 de 3 linhas importadas.",
        data=CsvImportResultDTO(
            origin_code="csv",
            received=3,
            accepted=2,
            duplicated=1,
            invalid=0,
            rows=[
                CsvRowResultDTO(line=2, description_id="csv-1", status=CsvRowStatus.ACCEPTED),
                CsvRowResultDTO(line=3, description_id="csv-2", status=CsvRowStatus.ACCEPTED),
                CsvRowResultDTO(line=4, description_id="csv-2", status=CsvRowStatus.DUPLICATED),
            ],
            transfer_run_id=12,
            transfer_queued=True,
        ),
    )

    response = client.post(
        "/api/v1/ingestion/csv",
        json={"rows": [{"line": 2, "description_id": "csv-1", "fields": {"Título": "A"}}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "CSV_IMPORT_QUEUED"
    assert body["data"]["accepted"] == 2
    assert body["data"]["review_status"] == "PENDING_AI"
    assert [row["status"] for row in body["data"]["rows"]] == ["ACCEPTED", "ACCEPTED", "DUPLICATED"]
    mock.assert_called_once()


def test_a_request_over_the_limit_answers_413_with_the_sentence(client: TestClient, mocker) -> None:
    mock = mocker.patch.object(
        IngestionOriginService,
        "import_csv",
        side_effect=CsvImportLimitError("A importação aceita no máximo 500 linhas por vez; o arquivo tem 501."),
    )

    response = client.post(
        "/api/v1/ingestion/csv",
        json={"rows": [{"description_id": "csv-1", "fields": {"Título": "A"}}]},
    )

    assert response.status_code == 413
    assert response.json()["error_code"] == "CsvImportLimitError"
    assert "500 linhas" in response.json()["message"]
    mock.assert_called_once()
