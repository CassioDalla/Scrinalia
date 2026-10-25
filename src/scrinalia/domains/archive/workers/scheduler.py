"""The scheduler: the process that turns a worker's cron into queue rows (ADR 0015).

It is exactly one process, and the database decides which one: every scheduler takes
``pg_try_advisory_lock`` on a fixed key for its lifetime; a second one stands by, retrying the lock,
so a crashed scheduler is replaced without an operator and a compose ``restart`` does not spin. On
top of the lock, each tick takes ``FOR UPDATE SKIP LOCKED`` on the due schedules, and the enqueue and
the ``next_run_at`` advance are one transaction: a crash between them cannot enqueue the same period
twice.

The tick enqueues **one** run per due schedule and advances to the next future occurrence. A period
that arrives while the worker already has a ``QUEUED``/``RUNNING`` row is skipped (the queue is one
slot per worker), and a scheduler that was down for several periods creates **one** catch-up run, not
a replay. It never retries a run itself: a retry is a new ledger row the next tick creates, and the
runner only claims and reports (ADR 0014).

The scheduler reads the same settings the panel does; the schedule's request is pinned, and the rest
of the configuration follows the persisted default at enqueue time. It has no model, no port and no
archive write authority.
"""

from __future__ import annotations

import argparse
import signal
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.core.config import get_settings
from scrinalia.core.database import SessionFactory, create_session
from scrinalia.core.logger import logger
from scrinalia.domains.archive.models.enums import WorkerRunTrigger
from scrinalia.domains.archive.models.operations import WorkerSchedule
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.repository.worker_schedule_repo import WorkerScheduleRepository
from scrinalia.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from scrinalia.domains.archive.schemas.system_schema import WorkerRunRequest
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE
from scrinalia.domains.archive.workers.configuration import resolve_configuration
from scrinalia.domains.archive.workers.retry import MAX_ATTEMPTS, retry_delay_seconds
from scrinalia.domains.archive.workers.schedule import next_occurrence
from scrinalia.domains.archive.workers.schema import assert_schema_at_head
from scrinalia.domains.ingestion.models import IngestionOrigin
from scrinalia.domains.ingestion.origin_registry import get_origin_summary
from scrinalia.domains.ingestion.origin_repo import IngestionOriginRepository
from scrinalia.domains.ingestion.schemas import IngestionRunRequest
from scrinalia.metadata import load_all_models

#: The advisory lock's key; one constant so every scheduler asks the same question. The value is
#: arbitrary — it only has to be stable and not collide with anything else that takes an advisory
#: lock in this database.
SCHEDULER_ADVISORY_LOCK = 0x5343_5249_4E41  # "SCRINA" in ASCII

#: The author the scheduled runs record. There is no session behind the scheduler; the trigger
#: (``SCHEDULE``) already says who asked, and the agenda's author is on the schedule row itself.
SCHEDULED_BY = Author("agenda")


@dataclass(frozen=True)
class SchedulerConfig:
    """What one scheduler process is: its tick and its patience."""

    tick_seconds: float = 30.0
    standby_seconds: float = 10.0
    once: bool = False


class SchedulerService:
    """The advisory lock, the tick and the enqueue/advance transaction of one scheduler."""

    def __init__(
        self,
        config: SchedulerConfig,
        *,
        session_factory: SessionFactory = create_session,
    ) -> None:
        self.config = config
        self._session_factory = session_factory
        self._stop = threading.Event()
        self._lock_session: Session | None = None

    def stop(self) -> None:
        """Asks the loop to finish the current tick and exit."""
        self._stop.set()

    def run(self) -> None:
        """Takes the lock, then ticks until a stop signal (or once with ``--once``)."""
        try:
            if not self._acquire():
                if self.config.once:
                    logger.warning("⏳ Another scheduler holds the lock; exiting (--once).")
                    return
                logger.warning("⏳ Another scheduler holds the lock; standing by.")
                self._standby()
            if self._lock_session is None:
                return
            if self.config.once:
                self.tick()
                return
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(self.config.tick_seconds)
        finally:
            self._release()

    def tick(self) -> int:
        """
        Processes every due schedule, in one transaction, and returns how many were due.

        Each schedule is its own savepoint so one broken row (a worker removed from the catalogue, a
        request that no longer validates) cannot abandon the others or lose their locks.
        """
        with self._session_factory() as db:
            now: datetime = db.execute(select(func.now())).scalar_one()
            retried = self._retry(db, now)
            schedules = WorkerScheduleRepository(db).due(now)
            for schedule in schedules:
                try:
                    with db.begin_nested():
                        self._process(db, schedule, now)
                except IntegrityError:
                    # A manual run won the race between the active check and this insert; the next
                    # tick sees the row and skips the period, like any other active run.
                    logger.info(f"⏭️ '{schedule.worker_name}' already has an active run; skipping this period.")
                except Exception as exc:
                    logger.error(f"⚠️ Could not schedule '{schedule.worker_name}': {exc}")
            origins = IngestionOriginRepository(db).due(now)
            for origin in origins:
                try:
                    with db.begin_nested():
                        self._process_origin(db, origin, now)
                except IntegrityError:
                    logger.info(f"⏭️ A origem '{origin.code}' já tem uma ingestão ativa; período pulado.")
                except Exception as exc:
                    logger.error(f"⚠️ Could not schedule the origin '{origin.code}': {exc}")
            db.commit()
            if schedules or origins or retried:
                logger.info(
                    f"🕒 Scheduler tick: {len(schedules)} due schedule(s), "
                    f"{len(origins)} due origin(s), {retried} retry(ies)."
                )
            return len(schedules) + len(origins)

    def _retry(self, db: Session, now: datetime) -> int:
        """
        Creates the retry row of every failed scheduled run that has none, and returns how many.

        A retry is a new ``QUEUED`` row with ``attempt + 1``, the previous request and config, and a
        ``not_before`` computed from the database's now plus the backoff. The row is created now and
        waits in the slot: the claim's ``not_before`` check keeps the runner from taking it early, and
        a manual run of the same worker answers 409 until then (ADR 0015).
        """
        failed = WorkerRunRepository(db).due_retries(MAX_ATTEMPTS)
        for run in failed:
            try:
                with db.begin_nested():
                    delay = retry_delay_seconds(run.attempt)
                    WorkerRunRepository(db).create_queued(
                        run.worker_name,
                        trigger=WorkerRunTrigger.SCHEDULE,
                        requested_by=SCHEDULED_BY,
                        engine_name=run.engine_name,
                        preset=run.preset,
                        config=dict(run.config or {}),
                        origin_code=run.origin_code,
                        request=dict(run.request or {}),
                        attempt=run.attempt + 1,
                        retry_of=run.id,
                        not_before=now + timedelta(seconds=delay),
                    )
                    logger.info(
                        f"🔁 Retry {run.attempt + 1}/{MAX_ATTEMPTS} of '{run.worker_name}' "
                        f"(run #{run.id}) in {delay} s."
                    )
            except IntegrityError:
                logger.info(f"⏭️ The retry of run #{run.id} lost the slot to another run; the next tick sees it.")
            except Exception as exc:
                logger.error(f"⚠️ Could not create the retry of run #{run.id}: {exc}")
        return len(failed)

    def _process(self, db: Session, schedule: WorkerSchedule, now: datetime) -> None:
        """Enqueues the run or skips the period, and always advances ``next_run_at``."""
        runs = WorkerRunRepository(db)
        if runs.has_active_run(schedule.worker_name):
            schedule.last_skipped_at = now
            schedule.next_run_at = next_occurrence(schedule.cron, schedule.timezone, now, previous=schedule.next_run_at)
            logger.info(f"⏭️ '{schedule.worker_name}' skipped: a run is already active.")
            return

        spec = WORKER_CATALOGUE.get(schedule.worker_name)
        if spec is None:
            # The catalogue is the definition; a row whose worker left it can never run. Skip the
            # period and keep the row visible, so the panel shows the stale agenda instead of it
            # disappearing (or the scheduler spinning on the same row).
            schedule.last_skipped_at = now
            schedule.next_run_at = next_occurrence(schedule.cron, schedule.timezone, now, previous=schedule.next_run_at)
            logger.warning(f"⚠️ The schedule of '{schedule.worker_name}' names a worker not in the catalogue.")
            return

        request = WorkerRunRequest.model_validate(schedule.request)
        setting = WorkerSettingsRepository(db).get(schedule.worker_name)
        resolved = resolve_configuration(
            db,
            spec,
            setting,
            engine_name=request.engine_name,
            preset=request.preset,
            db_batch_size=request.db_batch_size,
            options=request.options,
            engine_options=request.engine_options,
        )
        runs.create_queued(
            schedule.worker_name,
            trigger=WorkerRunTrigger.SCHEDULE,
            requested_by=SCHEDULED_BY,
            engine_name=resolved.engine_name,
            preset=resolved.preset,
            config=resolved.config,
            request=schedule.request,
        )
        schedule.last_enqueued_at = now
        schedule.next_run_at = next_occurrence(schedule.cron, schedule.timezone, now, previous=schedule.next_run_at)
        logger.info(f"🕒 Scheduled run for '{schedule.worker_name}' enqueued.")

    def _process_origin(self, db: Session, origin: IngestionOrigin, now: datetime) -> None:
        """
        The origin branch of the tick: one ``ingestion`` run per due origin, or a skipped period.

        The run's ``worker_name`` is the shared stage; the origin is the axis and travels in
        ``origin_code``. The queue is one slot per origin (the partial index includes the origin), so
        one origin's crawl does not wait behind another's. The request is the origin's persisted
        options, validated here exactly as the panel validates them.
        """
        runs = WorkerRunRepository(db)
        timezone = origin.timezone or get_settings().DEFAULT_TIMEZONE
        if runs.has_active_run("ingestion", origin.code):
            origin.last_skipped_at = now
            origin.next_run_at = next_occurrence(origin.cron or "", timezone, now, previous=origin.next_run_at)
            logger.info(f"⏭️ A origem '{origin.code}' foi pulada: já há uma ingestão ativa.")
            return

        try:
            get_origin_summary(origin.code)
            options = IngestionRunRequest.model_validate(origin.options or {}).model_dump(exclude_none=True)
        except Exception as exc:
            # The registry is the definition and the request model is the contract; a row that
            # names a removed origin or an invalid option can never run. Skip the period and keep
            # the row visible, like a stale worker schedule.
            origin.last_skipped_at = now
            origin.next_run_at = next_occurrence(origin.cron or "", timezone, now, previous=origin.next_run_at)
            logger.warning(f"⚠️ A agenda da origem '{origin.code}' não pode ser executada: {exc}")
            return

        runs.create_queued(
            "ingestion",
            trigger=WorkerRunTrigger.SCHEDULE,
            requested_by=SCHEDULED_BY,
            engine_name=None,
            preset=None,
            config={},
            origin_code=origin.code,
            request={"options": options},
        )
        origin.last_enqueued_at = now
        origin.next_run_at = next_occurrence(origin.cron or "", timezone, now, previous=origin.next_run_at)
        logger.info(f"🕒 Ingestão agendada para a origem '{origin.code}'.")

    def _acquire(self) -> bool:
        """Takes the advisory lock on a dedicated session; ``False`` when another scheduler holds it."""
        session = cast(Session, self._session_factory())
        try:
            acquired = session.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": SCHEDULER_ADVISORY_LOCK}
            ).scalar_one()
        except Exception:
            session.close()
            raise
        if acquired:
            self._lock_session = session
            return True
        session.close()
        return False

    def _standby(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.config.standby_seconds)
            if self.config.once:
                return
            if self._stop.is_set():
                return
            if self._acquire():
                return

    def _release(self) -> None:
        if self._lock_session is None:
            return
        try:
            self._lock_session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SCHEDULER_ADVISORY_LOCK})
        except Exception as exc:
            logger.warning(f"⚠️ Could not release the scheduler lock: {exc}")
        finally:
            self._lock_session.close()
            self._lock_session = None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Turn the workers' schedules into queue rows (ADR 0015).",
    )
    parser.add_argument("--tick-seconds", type=float, default=30.0, help="How often due schedules are checked.")
    parser.add_argument(
        "--standby-seconds",
        type=float,
        default=10.0,
        help="How often a standby scheduler retries the advisory lock.",
    )
    parser.add_argument("--once", action="store_true", help="Run one tick (or stand by once) and exit.")
    return parser.parse_args(argv)


def _build_config(args: argparse.Namespace) -> SchedulerConfig:
    """Validates the command line; a zero or negative interval is refused before the first tick."""
    if args.tick_seconds <= 0:
        raise SystemExit("--tick-seconds must be positive.")
    if args.standby_seconds <= 0:
        raise SystemExit("--standby-seconds must be positive.")
    return SchedulerConfig(
        tick_seconds=args.tick_seconds,
        standby_seconds=args.standby_seconds,
        once=args.once,
    )


def main(argv: list[str] | None = None) -> int:
    config = _build_config(_parse_args(argv))
    load_all_models()
    assert_schema_at_head(create_session)
    service = SchedulerService(config)
    signal.signal(signal.SIGTERM, lambda *_: service.stop())
    signal.signal(signal.SIGINT, lambda *_: service.stop())
    logger.info("🕒 Scheduler started.")
    service.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
