"""The execution ledger of the AI workers.

Every run writes here, whether it was started from the command line or from the panel: the ledger
is about the worker, not about the button. ``uq_worker_run_active`` (a partial unique index, see
``models/operations.py``) is the concurrency guard, so ``create_*`` must ``flush`` — that is when
PostgreSQL rejects a second in-flight run for the same worker.

The reads return DTOs, like ``CleaningRepository`` does: a ledger row is often read in a session
that is about to close (the ledger writer's own), and a detached ORM instance would explode on the
first attribute access.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models.enums import (
    ACTIVE_WORKER_RUN_STATUSES,
    WorkerRunStatus,
    WorkerRunTrigger,
)
from scrinalia.domains.archive.models.operations import MAX_ERROR_LENGTH, WorkerRun
from scrinalia.domains.archive.schemas.system_schema import WorkerRunDTO


def to_dto(run: WorkerRun) -> WorkerRunDTO:
    """Maps the row to the contract shape."""
    return WorkerRunDTO(
        run_id=run.id,
        worker_name=run.worker_name,
        status=run.status,
        trigger=run.trigger,
        requested_by=run.requested_by,
        engine_name=run.engine_name,
        preset=run.preset,
        config=dict(run.config or {}),
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=run.duration_ms,
        error=run.error,
        error_fingerprint=run.error_fingerprint,
    )


class WorkerRunRepository:
    """Reads and writes the run ledger; the caller owns the transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_queued(
        self,
        worker_name: str,
        *,
        trigger: WorkerRunTrigger,
        requested_by: str | None,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
    ) -> WorkerRunDTO:
        """Accepts a run before it starts, so the panel can show it waiting in the executor."""
        run = WorkerRun(
            worker_name=worker_name,
            status=WorkerRunStatus.QUEUED,
            trigger=trigger,
            requested_by=requested_by,
            engine_name=engine_name,
            preset=preset,
            config=config,
            queued_at=datetime.now(UTC),
        )
        self.db.add(run)
        self.db.flush()
        return to_dto(run)

    def create_running(
        self,
        worker_name: str,
        *,
        trigger: WorkerRunTrigger,
        requested_by: str | None,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
    ) -> WorkerRunDTO:
        """Opens a run that is already executing (the command line path)."""
        now = datetime.now(UTC)
        run = WorkerRun(
            worker_name=worker_name,
            status=WorkerRunStatus.RUNNING,
            trigger=trigger,
            requested_by=requested_by,
            engine_name=engine_name,
            preset=preset,
            config=config,
            queued_at=now,
            started_at=now,
        )
        self.db.add(run)
        self.db.flush()
        return to_dto(run)

    def mark_running(self, run_id: int) -> None:
        """Moves a queued run to running, which is when the executor's thread actually picks it up."""
        self.db.execute(
            update(WorkerRun)
            .where(WorkerRun.id == run_id, WorkerRun.status == WorkerRunStatus.QUEUED)
            .values(status=WorkerRunStatus.RUNNING, started_at=datetime.now(UTC))
        )
        self.db.flush()

    def finish(
        self,
        run_id: int,
        *,
        status: WorkerRunStatus,
        error: str | None = None,
        error_kind: str | None = None,
    ) -> None:
        """
        Closes the run with its outcome and duration.

        ``error`` is stored with the exception's class in front of it. ``str(exc)`` alone loses it,
        and the generated ``error_fingerprint`` column is computed from this text: without the class,
        two different failures that happen to share a sentence would group as one root cause.

        A bare ``raise RuntimeError()`` has a class and no message, and stores the class alone — the
        alternative would be recording *no* failure at all, which is the one outcome a ledger must
        not produce.
        """
        run = self.db.get(WorkerRun, run_id)
        if run is None:
            return

        finished_at = datetime.now(UTC)
        text = error or ""
        if error_kind:
            text = f"{error_kind}: {text}" if text else error_kind

        run.status = status
        run.finished_at = finished_at
        run.error = text[:MAX_ERROR_LENGTH] or None
        run.duration_ms = int((finished_at - run.started_at).total_seconds() * 1000) if run.started_at else None
        self.db.flush()

    def get(self, run_id: int) -> WorkerRunDTO | None:
        run = self.db.get(WorkerRun, run_id)
        return to_dto(run) if run is not None else None

    def list(
        self,
        *,
        worker_name: str | None = None,
        status: WorkerRunStatus | None = None,
        fingerprint: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkerRunDTO], int]:
        conditions = []
        if worker_name is not None:
            conditions.append(WorkerRun.worker_name == worker_name)
        if status is not None:
            conditions.append(WorkerRun.status == status)
        if fingerprint is not None:
            # The other half of the failures screen: a group is only actionable if the ledger can
            # show the occurrences behind it.
            conditions.append(WorkerRun.error_fingerprint == fingerprint)

        total = int(self.db.scalar(select(func.count()).select_from(WorkerRun).where(*conditions)) or 0)
        rows = self.db.scalars(
            select(WorkerRun)
            .where(*conditions)
            .order_by(WorkerRun.queued_at.desc(), WorkerRun.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [to_dto(run) for run in rows], total

    def last_by_worker(self) -> dict[str, WorkerRunDTO]:
        """The most recent run of each worker, one query for the whole panel."""
        rows = self.db.scalars(
            select(WorkerRun)
            .distinct(WorkerRun.worker_name)
            .order_by(WorkerRun.worker_name, WorkerRun.queued_at.desc(), WorkerRun.id.desc())
        ).all()
        return {run.worker_name: to_dto(run) for run in rows}

    def active_by_worker(self) -> dict[str, WorkerRunDTO]:
        """The runs in flight, keyed by worker; the partial unique index allows at most one each."""
        rows = self.db.scalars(select(WorkerRun).where(WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES))).all()
        return {run.worker_name: to_dto(run) for run in rows}

    def recover_orphans(self) -> int:
        """
        Marks the runs a dead process left behind.

        A row stuck at ``QUEUED``/``RUNNING`` is worse than a wrong one: the partial unique index
        would block that worker forever. Called once at start-up, with its own committed session,
        and it assumes a single API process — with several, it would kill a sibling's live run.
        """
        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRun)
                .where(WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES))
                .values(
                    status=WorkerRunStatus.INTERRUPTED,
                    finished_at=datetime.now(UTC),
                    error="O processo anterior terminou antes do fim desta execução.",
                )
            ),
        )
        self.db.flush()
        return int(result.rowcount or 0)
