"""The agenda service and the panel's schedule read, against the database (ADR 0015)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import (
    InvalidWorkerScheduleError,
    InvalidWorkerSettingsError,
    WorkerNotFoundError,
    WorkerScheduleNotFoundError,
)
from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.models.operations import WorkerRun
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.repository.worker_schedule_repo import WorkerScheduleRepository
from scrinalia.domains.archive.schemas.system_schema import WorkerScheduleRequest
from scrinalia.domains.archive.services.worker_operations_service import WorkerOperationsService
from scrinalia.domains.archive.services.worker_run_service import WorkerRunService
from scrinalia.domains.archive.services.worker_schedule_service import WorkerScheduleService
from scrinalia.domains.archive.workers.scheduler import SchedulerConfig, SchedulerService


@contextmanager
def _shared(db: Session) -> Iterator[Session]:
    yield db


def _request(**overrides) -> WorkerScheduleRequest:
    data: dict = {"cron": "0 2 * * *", "timezone": "UTC"}
    data.update(overrides)
    return WorkerScheduleRequest.model_validate(data)


def test_the_schedule_round_trips_with_the_next_run(db_session: Session) -> None:
    service = WorkerScheduleService(db_session)

    dto = service.upsert("cleaning", _request(), author=Author("ana"))

    assert dto.cron == "0 2 * * *"
    assert dto.timezone == "UTC"
    assert dto.next_run_at is not None and dto.next_run_at > datetime.now(UTC)
    assert dto.updated_by == "ana"

    read = service.get("cleaning")
    assert read is not None
    assert read.cron == "0 2 * * *"


def test_the_zone_defaults_to_the_instance_setting(db_session: Session) -> None:
    dto = WorkerScheduleService(db_session).upsert("cleaning", _request(timezone=None), author=Author("ana"))

    assert dto.timezone == "America/Sao_Paulo"


def test_the_pause_has_no_next_run_and_the_resume_recomputes_it(db_session: Session) -> None:
    service = WorkerScheduleService(db_session)

    paused = service.upsert("cleaning", _request(enabled=False), author=Author("ana"))
    assert paused.enabled is False
    assert paused.next_run_at is None

    resumed = service.upsert("cleaning", _request(enabled=True), author=Author("ana"))
    assert resumed.enabled is True
    assert resumed.next_run_at is not None


def test_a_four_field_cron_is_refused(db_session: Session) -> None:
    with pytest.raises(InvalidWorkerScheduleError, match="cinco campos"):
        WorkerScheduleService(db_session).upsert("cleaning", _request(cron="0 2 * *"), author=Author("ana"))


def test_an_unknown_zone_is_refused(db_session: Session) -> None:
    with pytest.raises(InvalidWorkerScheduleError):
        WorkerScheduleService(db_session).upsert("cleaning", _request(timezone="Mars/Olympus"), author=Author("ana"))


def test_a_request_the_worker_cannot_take_is_refused(db_session: Session) -> None:
    with pytest.raises(InvalidWorkerSettingsError):
        WorkerScheduleService(db_session).upsert(
            "cleaning", _request(request={"engine_name": "nope"}), author=Author("ana")
        )


def test_a_worker_out_of_the_catalogue_is_not_found(db_session: Session) -> None:
    with pytest.raises(WorkerNotFoundError):
        WorkerScheduleService(db_session).upsert("removed-worker", _request(), author=Author("ana"))


def test_deleting_removes_only_the_agenda_and_a_second_delete_is_not_found(db_session: Session) -> None:
    service = WorkerScheduleService(db_session)
    service.upsert("cleaning", _request(), author=Author("ana"))

    service.delete("cleaning")
    assert service.get("cleaning") is None

    with pytest.raises(WorkerScheduleNotFoundError):
        service.delete("cleaning")


def test_the_panel_carries_the_agenda_without_touching_the_counters(db_session: Session) -> None:
    now = datetime.now(UTC)
    WorkerScheduleRepository(db_session).upsert(
        "cleaning",
        enabled=True,
        cron="0 2 * * *",
        timezone="UTC",
        request={},
        next_run_at=now,
        author=Author("ana"),
    )
    db_session.flush()

    panel = WorkerOperationsService(db_session).list_workers()
    cleaning = next(worker for worker in panel.workers if worker.name == "cleaning")
    ner = next(worker for worker in panel.workers if worker.name == "ner")

    assert cleaning.schedule is not None
    assert cleaning.schedule.cron == "0 2 * * *"
    assert cleaning.schedule.next_run_at == now
    assert ner.schedule is None


def test_the_scheduler_enqueues_what_the_panel_saved(db_session: Session) -> None:
    now = datetime.now(UTC)
    WorkerScheduleService(db_session).upsert("cleaning", _request(cron="*/10 * * * *"), author=Author("ana"))
    schedule = WorkerScheduleRepository(db_session).get("cleaning")
    assert schedule is not None
    schedule.next_run_at = now - timedelta(minutes=1)
    db_session.flush()

    SchedulerService(SchedulerConfig(), session_factory=lambda: _shared(db_session)).tick()

    runs = list(db_session.scalars(select(WorkerRun).where(WorkerRun.worker_name == "cleaning")))
    assert len(runs) == 1
    assert runs[0].trigger == WorkerRunTrigger.SCHEDULE
    assert runs[0].status == WorkerRunStatus.QUEUED


def test_the_ledger_read_carries_the_attempt(db_session: Session) -> None:
    WorkerRunRepository(db_session).create_queued(
        "cleaning",
        trigger=WorkerRunTrigger.SCHEDULE,
        requested_by=None,
        engine_name=None,
        preset=None,
        config={},
        attempt=2,
    )
    db_session.flush()

    page = WorkerRunService(db_session).list_runs(worker_name=None, status=None, limit=20, offset=0)

    assert page.items[0].attempt == 2
