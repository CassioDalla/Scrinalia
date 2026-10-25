"""The schedule table: one cron row per worker (ADR 0015).

The scheduler and the panel's configuration write are the only writers, and both go through this
repository so the upsert, the due selection and the advance read the same row shape. The caller owns
the transaction: the scheduler's enqueue and advance must be one commit, or a crash between them
would enqueue the same period twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.core.author import Author, assign_author
from scrinalia.domains.archive.models.operations import WorkerSchedule


class WorkerScheduleRepository:
    """Reads and writes the agenda; the caller owns the transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, worker_name: str) -> WorkerSchedule | None:
        """The worker's schedule, or ``None`` when it has none."""
        return self.db.get(WorkerSchedule, worker_name)

    def list_all(self) -> list[WorkerSchedule]:
        """Every schedule, ordered by worker, for the panel's single read."""
        return list(self.db.scalars(select(WorkerSchedule).order_by(WorkerSchedule.worker_name)))

    def upsert(
        self,
        worker_name: str,
        *,
        enabled: bool,
        cron: str,
        timezone: str,
        request: dict[str, Any],
        next_run_at: datetime | None,
        author: Author | None,
    ) -> WorkerSchedule:
        """
        Creates or replaces the worker's agenda, leaving the last enqueued/skipped facts alone.

        ``updated_by`` is the person who saved the schedule; the scheduler's own writes (the advance
        and the skip) must not claim a human authored them, which is why they update the row directly
        and not through here.
        """
        schedule = self.db.get(WorkerSchedule, worker_name)
        if schedule is None:
            schedule = WorkerSchedule(worker_name=worker_name)
            self.db.add(schedule)
        schedule.enabled = enabled
        schedule.cron = cron
        schedule.timezone = timezone
        schedule.request = request
        schedule.next_run_at = next_run_at
        assign_author(schedule, "updated_by", author)
        self.db.flush()
        return schedule

    def delete(self, worker_name: str) -> bool:
        """Removes the agenda; the runs it already created stay in the ledger."""
        schedule = self.db.get(WorkerSchedule, worker_name)
        if schedule is None:
            return False
        self.db.delete(schedule)
        self.db.flush()
        return True

    def due(self, now: datetime) -> list[WorkerSchedule]:
        """
        The enabled schedules whose next run is at or before ``now``, locked for this transaction.

        ``FOR UPDATE SKIP LOCKED`` is the second guard after the advisory lock: a second scheduler —
        or a tick whose transaction overlapped a lock handover — skips a row another one is advancing
        instead of enqueueing the same period twice.
        """
        return list(
            self.db.scalars(
                select(WorkerSchedule)
                .where(
                    WorkerSchedule.enabled.is_(True),
                    WorkerSchedule.next_run_at.is_not(None),
                    WorkerSchedule.next_run_at <= now,
                )
                .order_by(WorkerSchedule.next_run_at, WorkerSchedule.worker_name)
                .with_for_update(skip_locked=True)
            )
        )
