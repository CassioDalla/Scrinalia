"""The execution ledger of the AI workers, and since ADR 0014 the queue they are claimed from.

Every run writes here, whether it was started from the command line or from the panel: the ledger
is about the worker, not about the button. ``uq_worker_run_active`` (a partial unique index, see
``models/operations.py``) is the concurrency guard, so ``create_*`` must ``flush`` — that is when
PostgreSQL rejects a second in-flight run for the same worker. It is also why the queue is one slot
per worker: a queued row already occupies the slot.

The queue protocol is the state machine of one row:

* ``claim_next`` moves the oldest ``QUEUED`` run this runner advertises to ``RUNNING`` with the
  runner's identity and a lease, in one statement (``FOR UPDATE SKIP LOCKED``).
* ``heartbeat`` renews the lease of the rows the runner still owns.
* ``record_start`` writes the configuration the run really resolved (the claim happened before the
  runner could resolve anything).
* ``finish`` closes the row, fenced by the runner that claimed it.
* ``expire_stale_leases`` marks only the claims whose lease expired as ``INTERRUPTED``; it is the
  runner's job, not the API's boot.

Every lease timestamp is computed by PostgreSQL's ``now()``: the API and the runner are different
machines, so the runner's clock cannot be the proof of life.

The reads return DTOs, like ``CleaningRepository`` does: a ledger row is often read in a session
that is about to close (the ledger writer's own), and a detached ORM instance would explode on the
first attribute access.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, Integer, func, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from scrinalia.core.author import Author, author_columns
from scrinalia.domains.archive.models.enums import (
    ACTIVE_WORKER_RUN_STATUSES,
    WorkerRunStatus,
    WorkerRunTrigger,
)
from scrinalia.domains.archive.models.operations import MAX_ERROR_LENGTH, WorkerRun
from scrinalia.domains.archive.schemas.system_schema import WorkerRunDTO

#: The error a swept claim is closed with. It names the cause (the runner stopped signalling) and
#: not a stack trace; the fingerprint groups every sweep under one root cause.
ORPHANED_CLAIM_ERROR = "O runner parou de enviar sinal antes do fim desta execução."


@dataclass(frozen=True)
class ClaimedRun:
    """What a claim returns: the row this runner now owns, with the request it must execute."""

    run_id: int
    worker_name: str
    request: dict[str, Any]


def _lease_deadline(lease_seconds: int) -> Any:
    """
    ``now()`` plus the lease, computed by PostgreSQL.

    Defined once so the claim and the heartbeat cannot drift into two different interval
    expressions. ``make_interval`` takes seconds as its seventh argument; a Python ``timedelta``
    would become a bind and make the statement's type depend on the driver.
    """
    return func.now() + func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds)


def _duration_ms() -> Any:
    """The duration of the run in milliseconds, computed by PostgreSQL from ``started_at``."""
    return sql_cast(func.extract("epoch", func.now() - WorkerRun.started_at) * 1000, Integer)


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
        options=dict(run.options or {}),
        queued_at=run.queued_at,
        runner_id=run.runner_id,
        started_at=run.started_at,
        heartbeat_at=run.heartbeat_at,
        lease_expires_at=run.lease_expires_at,
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
        requested_by: Author | None,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
        request: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> WorkerRunDTO:
        """
        Accepts a run before it starts, so the panel can show it waiting for a runner.

        ``request`` is the validated body this run was asked for. It is what makes the row a work
        item: the runner reproduces the execution from it without the process that accepted it
        (ADR 0014). ``config`` beside it is the resolution shown to the curator; it is a promise,
        and the runner writes the effective one when the run starts.
        """
        run = WorkerRun(
            worker_name=worker_name,
            status=WorkerRunStatus.QUEUED,
            trigger=trigger,
            **author_columns("requested_by", requested_by),
            engine_name=engine_name,
            preset=preset,
            request=request or {},
            config=config,
            options=options or {},
        )
        self.db.add(run)
        self.db.flush()
        # ``queued_at`` is PostgreSQL's clock, so the row is read back before it is serialised:
        # an unloaded server default would reach the contract as a SQL expression.
        self.db.refresh(run)
        return to_dto(run)

    def create_running(
        self,
        worker_name: str,
        *,
        trigger: WorkerRunTrigger,
        requested_by: Author | None,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
        request: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        runner_id: str | None = None,
        lease_seconds: int | None = None,
    ) -> WorkerRunDTO:
        """
        Opens a run that is already executing (the command line path).

        The CLI is a one-shot runner: it gives itself a ``runner_id`` and a lease so a crash is
        recovered by the next CLI or runner, exactly like a daemon's claim (ADR 0014).
        """
        run = WorkerRun(
            worker_name=worker_name,
            status=WorkerRunStatus.RUNNING,
            trigger=trigger,
            **author_columns("requested_by", requested_by),
            engine_name=engine_name,
            preset=preset,
            request=request or {},
            config=config,
            options=options or {},
            runner_id=runner_id,
            started_at=func.now(),
            heartbeat_at=func.now() if lease_seconds is not None else None,
            lease_expires_at=_lease_deadline(lease_seconds) if lease_seconds is not None else None,
        )
        self.db.add(run)
        self.db.flush()
        self.db.refresh(run)
        return to_dto(run)

    def claim_next(self, worker_names: Sequence[str], *, runner_id: str, lease_seconds: int) -> ClaimedRun | None:
        """
        Claims the oldest queued run this runner advertises, in one statement.

        ``FOR UPDATE SKIP LOCKED`` is the whole coordination: a second runner skips a row another
        one is claiming instead of waiting for it, and the partial unique index keeps at most one
        in-flight row per worker. The row becomes ``RUNNING`` with the runner's identity and a
        lease from PostgreSQL's clock, so the claim and the proof of life are one write. The caller
        owns the commit.
        """
        if not worker_names:
            return None

        next_run = (
            select(WorkerRun.id)
            .where(WorkerRun.status == WorkerRunStatus.QUEUED, WorkerRun.worker_name.in_(list(worker_names)))
            .order_by(WorkerRun.queued_at, WorkerRun.id)
            .with_for_update(skip_locked=True)
            .limit(1)
            .subquery("next_run")
        )
        row = self.db.execute(
            update(WorkerRun)
            .where(WorkerRun.id == next_run.c.id)
            .values(
                status=WorkerRunStatus.RUNNING,
                runner_id=runner_id,
                started_at=func.now(),
                heartbeat_at=func.now(),
                lease_expires_at=_lease_deadline(lease_seconds),
            )
            .returning(WorkerRun.id, WorkerRun.worker_name, WorkerRun.request)
        ).first()
        self.db.flush()
        if row is None:
            return None

        claimed_id, worker_name, request = row
        return ClaimedRun(run_id=int(claimed_id), worker_name=str(worker_name), request=dict(request or {}))

    def record_start(
        self,
        run_id: int,
        *,
        runner_id: str,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
        options: dict[str, Any],
    ) -> bool:
        """
        Records the configuration the claimed run really resolved, fenced to its runner.

        The claim moved the row to ``RUNNING`` before the runner could resolve anything (the engine
        may come from the persisted settings or from the active ``LLM_CHECK`` rule), so this is
        where the *effective* values are written. ``False`` means the row no longer belongs to this
        runner — the lease was swept — and the caller must not execute it.
        """
        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRun)
                .where(
                    WorkerRun.id == run_id,
                    WorkerRun.status == WorkerRunStatus.RUNNING,
                    WorkerRun.runner_id == runner_id,
                )
                .values(engine_name=engine_name, preset=preset, config=config, options=options)
            ),
        )
        self.db.flush()
        return bool(result.rowcount)

    def heartbeat(self, runner_id: str, *, lease_seconds: int, run_ids: Sequence[int] | None = None) -> int:
        """
        Renews the lease of the runs this runner owns; returns how many it renewed.

        ``run_ids`` lets the monitor renew exactly the rows it tracks. Without it the statement
        renews every ``RUNNING`` row of the runner, which is the same set in practice and a safer
        default after a restart.
        """
        conditions = [WorkerRun.runner_id == runner_id, WorkerRun.status == WorkerRunStatus.RUNNING]
        if run_ids is not None:
            if not run_ids:
                return 0
            conditions.append(WorkerRun.id.in_(list(run_ids)))

        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRun)
                .where(*conditions)
                .values(heartbeat_at=func.now(), lease_expires_at=_lease_deadline(lease_seconds))
            ),
        )
        self.db.flush()
        return int(result.rowcount or 0)

    def finish(
        self,
        run_id: int,
        *,
        status: WorkerRunStatus,
        error: str | None = None,
        error_kind: str | None = None,
        runner_id: str | None = None,
    ) -> bool:
        """
        Closes the run with its outcome and duration, computed by the database.

        ``error`` is stored with the exception's class in front of it. ``str(exc)`` alone loses it,
        and the generated ``error_fingerprint`` column is computed from this text: without the
        class, two different failures that happen to share a sentence would group as one root
        cause. A bare ``raise RuntimeError()`` stores the class alone — the alternative would be
        recording *no* failure at all, which is the one outcome a ledger must not produce.

        ``runner_id`` fences the write: when given, only the runner that claimed the row and only
        while it is ``RUNNING`` can close it. ``False`` is a lost lease, not a missing row; the
        caller logs it and does not pretend the outcome was recorded.
        """
        text = error or ""
        if error_kind:
            text = f"{error_kind}: {text}" if text else error_kind

        conditions = [WorkerRun.id == run_id]
        if runner_id is not None:
            conditions += [WorkerRun.runner_id == runner_id, WorkerRun.status == WorkerRunStatus.RUNNING]

        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRun)
                .where(*conditions)
                .values(
                    status=status,
                    finished_at=func.now(),
                    error=text[:MAX_ERROR_LENGTH] or None,
                    duration_ms=_duration_ms(),
                )
            ),
        )
        self.db.flush()
        return bool(result.rowcount)

    def expire_stale_leases(self) -> int:
        """
        Marks the claims whose lease expired as ``INTERRUPTED``, and only those.

        This is the orphan recovery that left the API (ADR 0014): a runner renews its rows, so an
        expired lease means the runner stopped signalling — a different process cannot know that
        about a sibling, but the database can. A live claim is untouched, which is what makes the
        sweep safe with several runners.
        """
        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRun)
                .where(
                    WorkerRun.status == WorkerRunStatus.RUNNING,
                    WorkerRun.lease_expires_at.is_not(None),
                    WorkerRun.lease_expires_at < func.now(),
                )
                .values(
                    status=WorkerRunStatus.INTERRUPTED,
                    finished_at=func.now(),
                    duration_ms=_duration_ms(),
                    error=ORPHANED_CLAIM_ERROR,
                )
            ),
        )
        self.db.flush()
        return int(result.rowcount or 0)

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
            .ext(distinct_on(WorkerRun.worker_name))
            .order_by(WorkerRun.worker_name, WorkerRun.queued_at.desc(), WorkerRun.id.desc())
        ).all()
        return {run.worker_name: to_dto(run) for run in rows}

    def active_by_worker(self) -> dict[str, WorkerRunDTO]:
        """The runs in flight, keyed by worker; the partial unique index allows at most one each."""
        rows = self.db.scalars(select(WorkerRun).where(WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES))).all()
        return {run.worker_name: to_dto(run) for run in rows}
