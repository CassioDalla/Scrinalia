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
from scrinalia.domains.ingestion.schemas import (
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
