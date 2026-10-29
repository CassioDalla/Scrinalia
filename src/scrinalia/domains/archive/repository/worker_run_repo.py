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
* ``close_unclaimed`` closes a ``QUEUED`` row no runner claimed as ``CANCELLED``; ``request_cancel``
  records the request on an in-flight row without freeing its slot, and ``is_cancel_requested`` is
  the read the worker performs once per batch (ADR 0014 decision 9, #72).

Every lease timestamp is computed by PostgreSQL's ``now()``: the API and the runner are different
machines, so the runner's clock cannot be the proof of life.

The reads return DTOs, like ``CleaningRepository`` does: a ledger row is often read in a session
that is about to close (the ledger writer's own), and a detached ORM instance would explode on the
first attribute access.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, Integer, exists, func, or_, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, aliased

from scrinalia.core.author import Author, author_columns
from scrinalia.domains.archive.models.enums import (
    ACTIVE_WORKER_RUN_STATUSES,
    WorkerRunStatus,
    WorkerRunTrigger,
)
from scrinalia.domains.archive.models.operations import MAX_ERROR_LENGTH, WorkerRun
from scrinalia.domains.archive.schemas.system_schema import WorkerRunDetailDTO, WorkerRunDTO, WorkerTrialResultDTO
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE

#: The error a swept claim is closed with. It names the cause (the runner stopped signalling) and
#: not a stack trace; the fingerprint groups every sweep under one root cause.
ORPHANED_CLAIM_ERROR = "O runner parou de enviar sinal antes do fim desta execução."


def _validate_axis(worker_name: str, origin_code: str | None, channel_code: str | None) -> None:
    """
    The ledger's one invariant: a run names the axis its worker has, and no other.

    The catalogue is the definition of which worker has which axis (``origin_axis`` for
    ``ingestion``, ``channel_axis`` for ``diffusion``), so the writer reads it instead of repeating
    the list. A run of an axis worker without its axis would share a slot with every other run of
    that worker (both columns coalesce to ``''``), and a run with both axes would be a slot no
    reader expects — the partial unique index cannot tell either apart, which is why this is a
    programming error and not a database constraint.

    A worker that is not in the catalogue is not refused: the ledger is allowed to remember a run of
    a worker that left the code, and the writer has no axis rule to apply to it.
    """
    spec = WORKER_CATALOGUE.get(worker_name)
    if spec is None:
        return
    if spec.origin_axis:
        if origin_code is None or channel_code is not None:
            raise ValueError(f"a run of '{worker_name}' names the origin and no channel")
    elif spec.channel_axis:
        if channel_code is None or origin_code is not None:
            raise ValueError(f"a run of '{worker_name}' names the channel and no origin")
    elif origin_code is not None or channel_code is not None:
        raise ValueError(f"a run of '{worker_name}' names neither an origin nor a channel")


@dataclass(frozen=True)
class ClaimedRun:
    """What a claim returns: the row this runner now owns, with the request it must execute."""

    run_id: int
    worker_name: str
    #: The origin an ingestion run processes; ``None`` for an archive worker.
    origin_code: str | None
    request: dict[str, Any]
    #: The channel a diffusion run writes; ``None`` for every other worker (ADR 0023).
    channel_code: str | None = None
    #: True when this row is a trial comparison rather than a production execution (ADR 0018). The
    #: runner dispatches on it: a trial runs the configurations over a sample and writes no
    #: archival content, while a production run calls the worker.
    trial: bool = False


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
        origin_code=run.origin_code,
        channel_code=run.channel_code,
        status=run.status,
        trigger=run.trigger,
        trial=run.trial,
        attempt=run.attempt,
        retry_of=run.retry_of,
        not_before=run.not_before,
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
        cancel_requested_at=run.cancel_requested_at,
        cancel_requested_by=run.cancel_requested_by,
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
        origin_code: str | None = None,
        channel_code: str | None = None,
        request: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        attempt: int = 1,
        retry_of: int | None = None,
        not_before: datetime | None = None,
        trial: bool = False,
    ) -> WorkerRunDTO:
        """
        Accepts a run before it starts, so the panel can show it waiting for a runner.

        ``request`` is the validated body this run was asked for. It is what makes the row a work
        item: the runner reproduces the execution from it without the process that accepted it
        (ADR 0014). ``config`` beside it is the resolution shown to the curator; it is a promise,
        and the runner writes the effective one when the run starts.

        ``origin_code``/``channel_code`` are the run's **axis**: ``ingestion`` names the origin,
        ``diffusion`` names the channel, and every other worker names neither. ``_validate_axis``
        is the one check, against the catalogue.

        ``attempt``/``retry_of``/``not_before`` are the scheduler's (ADR 0015): a retry is a new row
        created after the previous one is terminal. A manual/CLI run leaves them at 1/None/None.
        ``trial`` marks a comparison of configurations (ADR 0018); its request carries the configs
        and its ``config`` is deliberately empty, because there is no single resolved configuration
        until the runner measures them.
        """
        _validate_axis(worker_name, origin_code, channel_code)
        run = WorkerRun(
            worker_name=worker_name,
            origin_code=origin_code,
            channel_code=channel_code,
            status=WorkerRunStatus.QUEUED,
            trigger=trigger,
            trial=trial,
            attempt=attempt,
            retry_of=retry_of,
            not_before=not_before,
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
        origin_code: str | None = None,
        channel_code: str | None = None,
        request: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        runner_id: str | None = None,
        lease_seconds: int | None = None,
    ) -> WorkerRunDTO:
        """
        Opens a run that is already executing (the command line path).

        The CLI is a one-shot runner: it gives itself a ``runner_id`` and a lease so a crash is
        recovered by the next CLI or runner, exactly like a daemon's claim (ADR 0014). The axis is
        validated like ``create_queued``'s: a CLI run of ``diffusion`` names the channel.
        """
        _validate_axis(worker_name, origin_code, channel_code)
        run = WorkerRun(
            worker_name=worker_name,
            origin_code=origin_code,
            channel_code=channel_code,
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

    def has_active_run(
        self,
        worker_name: str,
        origin_code: str | None = None,
        channel_code: str | None = None,
    ) -> bool:
        """
        Whether the worker already has a ``QUEUED``/``RUNNING`` row: the scheduler's skip check.

        ``origin_code`` narrows the question to one origin's slot and ``channel_code`` to one
        channel's; the archive workers pass neither and keep their one-slot-per-worker guard.
        """
        conditions = [
            WorkerRun.worker_name == worker_name,
            WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES),
        ]
        if origin_code is None:
            conditions.append(WorkerRun.origin_code.is_(None))
        else:
            conditions.append(WorkerRun.origin_code == origin_code)
        if channel_code is None:
            conditions.append(WorkerRun.channel_code.is_(None))
        else:
            conditions.append(WorkerRun.channel_code == channel_code)
        return bool(self.db.scalar(select(exists().where(*conditions))))

    def due_retries(self, max_attempts: int) -> list[WorkerRun]:
        """
        The ``SCHEDULE`` runs that ended ``FAILED``/``INTERRUPTED`` and have no retry yet.

        The status check is the eligibility rule (ADR 0014): a manual or CLI run is never retried,
        and a success has nothing to retry. ``attempt < max_attempts`` enforces the three-attempt
        bound at the query, and the correlated ``NOT EXISTS`` is what makes the tick idempotent — a
        crash after creating the retry does not create a second one on the next tick. The rows are
        locked so the advisory lock's owner and a concurrent sweep cannot both retry the same row.
        """
        child = aliased(WorkerRun)
        return list(
            self.db.scalars(
                select(WorkerRun)
                .where(
                    WorkerRun.trigger == WorkerRunTrigger.SCHEDULE,
                    WorkerRun.status.in_((WorkerRunStatus.FAILED, WorkerRunStatus.INTERRUPTED)),
                    WorkerRun.attempt < max_attempts,
                    ~exists().where(child.retry_of == WorkerRun.id),
                )
                .order_by(WorkerRun.finished_at, WorkerRun.id)
                .with_for_update(skip_locked=True)
            )
        )

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
            .where(
                WorkerRun.status == WorkerRunStatus.QUEUED,
                WorkerRun.worker_name.in_(list(worker_names)),
                # A retry carries the moment its backoff ends; until then it waits in the slot without
                # being claimable (ADR 0015).
                or_(WorkerRun.not_before.is_(None), WorkerRun.not_before <= func.now()),
            )
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
            .returning(
                WorkerRun.id,
                WorkerRun.worker_name,
                WorkerRun.origin_code,
                WorkerRun.channel_code,
                WorkerRun.request,
                WorkerRun.trial,
            )
        ).first()
        self.db.flush()
        if row is None:
            return None

        claimed_id, worker_name, origin_code, channel_code, request, trial = row
        return ClaimedRun(
            run_id=int(claimed_id),
            worker_name=str(worker_name),
            origin_code=str(origin_code) if origin_code is not None else None,
            request=dict(request or {}),
            channel_code=str(channel_code) if channel_code is not None else None,
            trial=bool(trial),
        )

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
        trial_result: dict[str, Any] | None = None,
    ) -> bool:
        """
        Closes the run with its outcome and duration, computed by the database.

        ``error`` is stored with the exception's class in front of it. ``str(exc)`` alone loses it,
        and the generated ``error_fingerprint`` column is computed from this text: without the
        class, two different failures that happen to share a sentence would group as one root
        cause. A bare ``raise RuntimeError()`` stores the class alone — the alternative would be
        recording *no* failure at all, which is the one outcome a ledger must not produce.

        ``trial_result`` is the comparison's evidence, written once in the same closing statement
        (ADR 0018). A production run passes none and the column stays ``NULL``.

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

        values: dict[str, Any] = {
            "status": status,
            "finished_at": func.now(),
            "error": text[:MAX_ERROR_LENGTH] or None,
            "duration_ms": _duration_ms(),
        }
        if trial_result is not None:
            values["trial_result"] = trial_result

        result = cast(
            CursorResult[Any],
            self.db.execute(update(WorkerRun).where(*conditions).values(**values)),
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

    def close_unclaimed(self, run_id: int, *, requested_by: Author | None) -> bool:
        """
        Closes a ``QUEUED`` row no runner has claimed as ``CANCELLED``, in one statement.

        The predicate is the whole race: a claim that wins between the panel's read and this write
        moves the row to ``RUNNING``, this update matches nothing, and the caller falls back to
        ``request_cancel``. The slot is released only when nothing is running, which is the
        distinction ADR 0014 decision 9 draws. ``duration_ms`` is NULL because ``started_at`` is:
        the run never started, and a duration would be invented.
        """
        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRun)
                .where(
                    WorkerRun.id == run_id,
                    WorkerRun.status == WorkerRunStatus.QUEUED,
                    WorkerRun.runner_id.is_(None),
                )
                .values(
                    status=WorkerRunStatus.CANCELLED,
                    cancel_requested_at=func.now(),
                    finished_at=func.now(),
                    duration_ms=_duration_ms(),
                    **author_columns("cancel_requested_by", requested_by),
                )
            ),
        )
        self.db.flush()
        return bool(result.rowcount)

    def request_cancel(self, run_id: int, *, requested_by: Author | None) -> bool:
        """
        Records the cancellation request without touching the status or the slot.

        ``cancel_requested_at`` is a request, not a state: the row stays ``QUEUED``/``RUNNING`` and
        keeps ``uq_worker_run_active`` until the worker honours it at a batch boundary. Idempotent:
        the second request finds the column already set and matches nothing, so the first author and
        the first instant survive.
        """
        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRun)
                .where(
                    WorkerRun.id == run_id,
                    WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES),
                    WorkerRun.cancel_requested_at.is_(None),
                )
                .values(
                    cancel_requested_at=func.now(),
                    **author_columns("cancel_requested_by", requested_by),
                )
            ),
        )
        self.db.flush()
        return bool(result.rowcount)

    def is_cancel_requested(self, run_id: int) -> bool:
        """Whether a cancellation was requested for this run; the runner reads it once per batch."""
        return self.db.scalar(select(WorkerRun.cancel_requested_at).where(WorkerRun.id == run_id)) is not None

    def is_owned(self, run_id: int, runner_id: str) -> bool:
        """
        Whether this runner still owns a run in flight.

        The trial's fence (ADR 0018): the claim wrote ``runner_id`` and ``RUNNING``, but a lease
        swept between the claim and the first model call must abort before the work is paid for,
        exactly as ``run_worker``'s ``record_start`` does for a production run. A trial has no one
        effective configuration to record, so it checks the ownership without writing one.
        """
        return bool(
            self.db.scalar(
                select(
                    exists().where(
                        WorkerRun.id == run_id,
                        WorkerRun.status == WorkerRunStatus.RUNNING,
                        WorkerRun.runner_id == runner_id,
                    )
                )
            )
        )

    def get(self, run_id: int, *, populate_existing: bool = False) -> WorkerRunDTO | None:
        """
        One row as the contract reads it.

        ``populate_existing`` re-reads a row this session just updated: without it SQLAlchemy
        returns the identity-mapped instance and the caller would serialise the state *before* its
        own write — the exact stale read the cancellation's response cannot afford.
        """
        run = self.db.get(WorkerRun, run_id, populate_existing=populate_existing)
        return to_dto(run) if run is not None else None

    def get_detail(self, run_id: int) -> WorkerRunDetailDTO | None:
        """
        One row plus the trial result, when it is a trial (ADR 0018).

        The list stays light: ``trial_result`` can carry the sampled ids and the per-configuration
        tables, and the ledger pages over runs that are not trials at all. The comparison card asks
        for the one run it is showing.
        """
        run = self.db.get(WorkerRun, run_id)
        if run is None:
            return None
        result = WorkerTrialResultDTO.model_validate(run.trial_result) if run.trial_result else None
        return WorkerRunDetailDTO(**to_dto(run).model_dump(), trial_result=result)

    def list(
        self,
        *,
        worker_name: str | None = None,
        origin_code: str | None = None,
        channel_code: str | None = None,
        status: WorkerRunStatus | None = None,
        fingerprint: str | None = None,
        trial: bool | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkerRunDTO], int]:
        conditions = []
        if worker_name is not None:
            conditions.append(WorkerRun.worker_name == worker_name)
        if origin_code is not None:
            conditions.append(WorkerRun.origin_code == origin_code)
        if channel_code is not None:
            conditions.append(WorkerRun.channel_code == channel_code)
        if status is not None:
            conditions.append(WorkerRun.status == status)
        if fingerprint is not None:
            # The other half of the failures screen: a group is only actionable if the ledger can
            # show the occurrences behind it.
            conditions.append(WorkerRun.error_fingerprint == fingerprint)
        if trial is not None:
            # The comparison card reads the latest trial of one worker; the ledger's other readers
            # leave it unset and see production and trials alike (ADR 0018).
            conditions.append(WorkerRun.trial.is_(trial))

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
        """
        The most recent **production** run of each worker, one query for the whole panel.

        A trial never answers "when did this worker last run?": it writes no archival content, so
        showing it as the worker's last run would make the panel describe an experiment as work
        (ADR 0018). A trial in flight is still the worker's active run, because it holds the slot.
        """
        rows = self.db.scalars(
            select(WorkerRun)
            .where(WorkerRun.trial.is_(False))
            .ext(distinct_on(WorkerRun.worker_name))
            .order_by(WorkerRun.worker_name, WorkerRun.queued_at.desc(), WorkerRun.id.desc())
        ).all()
        return {run.worker_name: to_dto(run) for run in rows}

    def active_by_worker(self) -> dict[str, WorkerRunDTO]:
        """The runs in flight, keyed by worker; the partial unique index allows at most one each."""
        rows = self.db.scalars(select(WorkerRun).where(WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES))).all()
        return {run.worker_name: to_dto(run) for run in rows}

    def last_ingestion_by_origin(self) -> dict[str, WorkerRunDTO]:
        """The most recent ingestion run of each origin, one query for the ingestion screen."""
        rows = self.db.scalars(
            select(WorkerRun)
            .where(WorkerRun.worker_name == "ingestion")
            .ext(distinct_on(WorkerRun.origin_code))
            .order_by(WorkerRun.origin_code, WorkerRun.queued_at.desc(), WorkerRun.id.desc())
        ).all()
        return {run.origin_code: to_dto(run) for run in rows if run.origin_code is not None}

    def active_ingestion_by_origin(self) -> dict[str, WorkerRunDTO]:
        """The ingestion runs in flight, keyed by origin; one slot per origin."""
        rows = self.db.scalars(
            select(WorkerRun).where(
                WorkerRun.worker_name == "ingestion",
                WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES),
            )
        ).all()
        return {run.origin_code: to_dto(run) for run in rows if run.origin_code is not None}

    def last_diffusion_by_channel(self) -> dict[str, WorkerRunDTO]:
        """The most recent diffusion run of each channel, one query for the operator page."""
        rows = self.db.scalars(
            select(WorkerRun)
            .where(WorkerRun.worker_name == "diffusion")
            .ext(distinct_on(WorkerRun.channel_code))
            .order_by(WorkerRun.channel_code, WorkerRun.queued_at.desc(), WorkerRun.id.desc())
        ).all()
        return {run.channel_code: to_dto(run) for run in rows if run.channel_code is not None}

    def active_diffusion_by_channel(self) -> dict[str, WorkerRunDTO]:
        """The diffusion runs in flight, keyed by channel; one slot per channel."""
        rows = self.db.scalars(
            select(WorkerRun).where(
                WorkerRun.worker_name == "diffusion",
                WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES),
            )
        ).all()
        return {run.channel_code: to_dto(run) for run in rows if run.channel_code is not None}
