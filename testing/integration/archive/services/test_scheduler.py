"""The scheduler: the due selection, the enqueue, the skip and the catch-up (ADR 0015).

The service commits through the session it is given, so the test hands it the fixture's session
through a context manager that does not close it: the savepoint isolation still rolls everything back
at the end of the test.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from scrinalia.core.author import Author
from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.models.operations import WorkerRun
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.repository.worker_schedule_repo import WorkerScheduleRepository
from scrinalia.domains.archive.workers.scheduler import SchedulerConfig, SchedulerService


@contextmanager
def _shared(db: Session) -> Iterator[Session]:
    """Hands the test's session to the scheduler without closing it on the way out."""
    yield db


def _service(db: Session) -> SchedulerService:
    return SchedulerService(SchedulerConfig(), session_factory=lambda: _shared(db))


def _schedule(
    db: Session,
    *,
    worker: str = "cleaning",
    next_run_at: datetime,
    cron: str = "*/10 * * * *",
    enabled: bool = True,
) -> None:
    WorkerScheduleRepository(db).upsert(
        worker,
        enabled=enabled,
        cron=cron,
        timezone="UTC",
        request={},
        next_run_at=next_run_at,
        author=Author("test"),
    )


def _count(db: Session, worker: str = "cleaning") -> int:
    return db.scalar(select(func.count()).select_from(WorkerRun).where(WorkerRun.worker_name == worker)) or 0


def test_a_due_schedule_enqueues_one_run_and_advances(db_session: Session) -> None:
    now = datetime.now(UTC)
    _schedule(db_session, next_run_at=now - timedelta(minutes=1))

    assert _service(db_session).tick() == 1

    runs = list(db_session.scalars(select(WorkerRun).where(WorkerRun.worker_name == "cleaning")))
    assert len(runs) == 1
    assert runs[0].trigger == WorkerRunTrigger.SCHEDULE
    assert runs[0].attempt == 1
    assert runs[0].status.value == "QUEUED"
    assert runs[0].request == {}

    schedule = WorkerScheduleRepository(db_session).get("cleaning")
    assert schedule is not None
    assert schedule.last_enqueued_at is not None
    assert schedule.next_run_at is not None and schedule.next_run_at > now


def test_a_future_schedule_is_not_due(db_session: Session) -> None:
    _schedule(db_session, next_run_at=datetime.now(UTC) + timedelta(hours=1))

    assert _service(db_session).tick() == 0
    assert _count(db_session) == 0


def test_a_disabled_schedule_is_not_due(db_session: Session) -> None:
    _schedule(db_session, next_run_at=datetime.now(UTC) - timedelta(minutes=1), enabled=False)

    assert _service(db_session).tick() == 0
    assert _count(db_session) == 0


def test_a_due_schedule_is_skipped_while_a_run_is_active(db_session: Session) -> None:
    now = datetime.now(UTC)
    _schedule(db_session, next_run_at=now - timedelta(minutes=1))
    WorkerRunRepository(db_session).create_queued(
        "cleaning",
        trigger=WorkerRunTrigger.API,
        requested_by=None,
        engine_name=None,
        preset=None,
        config={},
    )
    db_session.flush()

    assert _service(db_session).tick() == 1

    assert _count(db_session) == 1
    schedule = WorkerScheduleRepository(db_session).get("cleaning")
    assert schedule is not None
    assert schedule.last_skipped_at is not None
    assert schedule.next_run_at is not None and schedule.next_run_at > now


def test_a_missed_period_is_one_catch_up_not_a_replay(db_session: Session) -> None:
    now = datetime.now(UTC)
    _schedule(db_session, next_run_at=now - timedelta(hours=3), cron="0 * * * *")

    assert _service(db_session).tick() == 1

    assert _count(db_session) == 1
    schedule = WorkerScheduleRepository(db_session).get("cleaning")
    assert schedule is not None
    assert schedule.next_run_at is not None and schedule.next_run_at > now
    # The next hour, not the two intervals the scheduler was down for.
    assert schedule.next_run_at - now <= timedelta(hours=1)


def test_a_schedule_for_a_worker_out_of_the_catalogue_is_skipped(db_session: Session) -> None:
    now = datetime.now(UTC)
    _schedule(db_session, worker="removed-worker", next_run_at=now - timedelta(minutes=1))

    assert _service(db_session).tick() == 1

    assert _count(db_session, "removed-worker") == 0
    schedule = WorkerScheduleRepository(db_session).get("removed-worker")
    assert schedule is not None
    assert schedule.last_skipped_at is not None
    assert schedule.next_run_at is not None and schedule.next_run_at > now


def test_only_one_scheduler_holds_the_advisory_lock(engine) -> None:
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    first = SchedulerService(SchedulerConfig(), session_factory=factory)
    second = SchedulerService(SchedulerConfig(), session_factory=factory)

    assert first._acquire() is True
    assert second._acquire() is False

    first._release()
    assert second._acquire() is True
    second._release()


def _failed(
    db: Session,
    *,
    trigger: WorkerRunTrigger = WorkerRunTrigger.SCHEDULE,
    status: WorkerRunStatus = WorkerRunStatus.FAILED,
    attempt: int = 1,
    worker: str = "cleaning",
) -> WorkerRun:
    run = WorkerRun(
        worker_name=worker,
        status=status,
        trigger=trigger,
        attempt=attempt,
        engine_name=None,
        preset=None,
        request={},
        config={},
        finished_at=datetime.now(UTC),
    )
    db.add(run)
    db.flush()
    return run


def _retries(db: Session, failed_id: int) -> list[WorkerRun]:
    return list(db.scalars(select(WorkerRun).where(WorkerRun.retry_of == failed_id)))


def test_a_failed_scheduled_run_is_retried(db_session: Session) -> None:
    failed = _failed(db_session)

    assert _service(db_session).tick() == 0

    retry = _retries(db_session, failed.id)
    assert len(retry) == 1
    assert retry[0].attempt == 2
    assert retry[0].trigger == WorkerRunTrigger.SCHEDULE
    assert retry[0].status == WorkerRunStatus.QUEUED
    assert retry[0].not_before is not None
    assert retry[0].not_before > datetime.now(UTC) + timedelta(seconds=30)
    assert retry[0].request == {}


def test_a_manual_failed_run_is_not_retried(db_session: Session) -> None:
    _failed(db_session, trigger=WorkerRunTrigger.API)

    assert _service(db_session).tick() == 0
    assert _retries(db_session, 0) == []


def test_a_cli_failed_run_is_not_retried(db_session: Session) -> None:
    _failed(db_session, trigger=WorkerRunTrigger.CLI)

    assert _service(db_session).tick() == 0
    assert _retries(db_session, 0) == []


def test_a_third_attempt_is_not_retried(db_session: Session) -> None:
    _failed(db_session, attempt=3)

    assert _service(db_session).tick() == 0
    assert _retries(db_session, 0) == []


def test_an_interrupted_scheduled_run_is_retried(db_session: Session) -> None:
    failed = _failed(db_session, status=WorkerRunStatus.INTERRUPTED)

    assert _service(db_session).tick() == 0

    retry = _retries(db_session, failed.id)
    assert len(retry) == 1
    assert retry[0].attempt == 2


def test_a_retry_is_not_duplicated(db_session: Session) -> None:
    failed = _failed(db_session)
    service = _service(db_session)

    assert service.tick() == 0
    assert service.tick() == 0

    assert len(_retries(db_session, failed.id)) == 1


def test_a_retry_before_its_not_before_is_not_claimed(db_session: Session) -> None:
    now = datetime.now(UTC)
    run_id = (
        WorkerRunRepository(db_session)
        .create_queued(
            "cleaning",
            trigger=WorkerRunTrigger.SCHEDULE,
            requested_by=None,
            engine_name=None,
            preset=None,
            config={},
            attempt=2,
            not_before=now + timedelta(hours=1),
        )
        .run_id
    )
    db_session.flush()

    assert WorkerRunRepository(db_session).claim_next(["cleaning"], runner_id="r1", lease_seconds=60) is None

    run = db_session.get(WorkerRun, run_id)
    assert run is not None
    run.not_before = now - timedelta(minutes=1)
    db_session.flush()

    claimed = WorkerRunRepository(db_session).claim_next(["cleaning"], runner_id="r1", lease_seconds=60)
    assert claimed is not None
    assert claimed.run_id == run_id


def test_the_schedule_skips_while_the_retry_is_queued(db_session: Session) -> None:
    now = datetime.now(UTC)
    _failed(db_session)
    _schedule(db_session, next_run_at=now - timedelta(minutes=1))

    assert _service(db_session).tick() == 1

    assert _count(db_session) == 2  # the failed row and its retry, not a third scheduled run
    schedule = WorkerScheduleRepository(db_session).get("cleaning")
    assert schedule is not None
    assert schedule.last_skipped_at is not None
