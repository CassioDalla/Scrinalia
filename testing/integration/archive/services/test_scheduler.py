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
from scrinalia.domains.archive.models.enums import WorkerRunTrigger
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
