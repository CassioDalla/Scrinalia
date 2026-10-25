"""Operational state of the AI workers: persisted defaults, the execution ledger and its runners.

Three concerns live here, all owned by the *operation* of the system rather than by the archival
record:

* ``WorkerSetting`` — the default engine/preset/batch/options of a worker, which the runner uses
  when the command line says nothing. ``WorkerSettingRevision`` is its audit trail, in the same
  spirit as ``ArchiveDocumentRevision``: the decision and the write are different facts.
* ``WorkerRun`` — one line per execution, written by the runner for **both** the CLI and the panel,
  so the ledger is about the worker and not about the button that started it. Since ADR 0014 the
  ``QUEUED`` row is also the **work item** the external runner claims, and the row carries the
  request it was asked for, the runner that holds it and the lease that proves the runner is alive.
* ``WorkerRunner`` — the live runner registry: who is connected, which workers it accepts, and
  when it last said so. It is what lets the panel answer "why did nothing happen?".
  * ``WorkerSchedule`` — the agenda of one worker: a five-field cron in an explicit timezone and the
  request it runs. It survives a restart and is what the scheduler reads (ADR 0015).

There is deliberately **no foreign key to a worker table**: workers are code, not rows. A run whose
worker was later removed from the catalogue stays readable, which is what a ledger is for.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Computed, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base

from .enums import WorkerRunStatus, WorkerRunTrigger

#: Literal form of the partial index predicate. Kept next to the index so the model, the migration
#: and any hand-written query read the same words; ``ACTIVE_WORKER_RUN_STATUSES`` owns the meaning.
ACTIVE_RUN_PREDICATE = "status IN ('QUEUED', 'RUNNING')"

#: The queue's index: the claim reads the oldest ``QUEUED`` row, and only those rows are the queue.
QUEUED_RUN_PREDICATE = "status = 'QUEUED'"

#: The lease's index: the sweeper and the heartbeat only ever look at the runs in flight.
RUNNING_RUN_PREDICATE = "status = 'RUNNING'"

#: The expression of the generated ``error_fingerprint`` column. ``public.`` is spelled out because
#: that is how PostgreSQL reflects the expression back: without it ``alembic check`` would report a
#: difference that is not one. The function itself is created by the migration and mirrored in
#: ``testing/conftest.py``, exactly like ``immutable_unaccent`` — the test schema is built from the
#: models, so the function has to exist before ``create_all`` emits this expression.
WORKER_RUN_ERROR_FINGERPRINT_SQL = "public.archive_error_fingerprint(error)"

#: How much of an exception both ledgers keep. Enough to act on, not a stack-trace store. It lives
#: next to the two error columns so the two writers cannot drift into keeping different amounts.
MAX_ERROR_LENGTH = 2000

_EMPTY_JSON = text("'{}'::jsonb")


class WorkerSetting(Base):
    """
    Persisted default configuration of one worker.

    The precedence the runner applies is ``explicit argument > this row > the signature default``.
    Storing a partial row (only the fields the operator changed) is deliberate: a field left
    ``NULL`` means "keep following the code", so a preset renamed in a new release still reaches
    every worker nobody overrode.
    """

    __tablename__ = "archive_worker_settings"

    worker_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    engine_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    db_batch_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WorkerSettingRevision(Base):
    """Audit trail of the configuration changes, one row per write."""

    __tablename__ = "archive_worker_settings_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WorkerRun(Base):
    """
    One execution of a worker, from the queue to the outcome.

    Since ADR 0014 a ``QUEUED`` row is also the **work item**: an external runner claims it with
    ``FOR UPDATE SKIP LOCKED``, and the row carries the request (``request``), the runner that holds
    it (``runner_id``) and the lease that proves that runner is still alive (``heartbeat_at``,
    ``lease_expires_at``). ``config`` is the **resolved** configuration (the preset already merged
    with the overrides), so the row keeps its meaning when a preset changes in code; ``options`` is
    the resolved set of the worker's own options, so "which columns did this run read?" is a value
    and not a fingerprint. ``error`` is the exception text, prefixed with its class
    (``ValueError: ...``) and truncated: enough to act on, not a stack trace storage.
    ``error_fingerprint`` is the *root cause* of that text, computed by PostgreSQL — see the column
    below.

    ``cancel_requested_at`` is the operator's **request**, not a status: the row stays
    ``QUEUED``/``RUNNING`` and keeps ``uq_worker_run_active`` until the request is honoured, because
    releasing the slot while the worker is still writing would let a second run overlap it
    (ADR 0014 decision 9). A ``QUEUED`` row no runner has claimed is closed ``CANCELLED`` by the
    API at once; a claimed one stops at the next batch boundary. ``cancel_requested_by`` is the
    account that asked, and it is deliberately a second pair of columns rather than a reuse of
    ``requested_by``: "who started it" and "who stopped it" are two decisions, and a cancellation
    may be asked by someone else.
    """

    __tablename__ = "archive_worker_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[WorkerRunStatus] = mapped_column(
        Enum(WorkerRunStatus, name="worker_run_status"), nullable=False, index=True
    )
    trigger: Mapped[WorkerRunTrigger] = mapped_column(Enum(WorkerRunTrigger, name="worker_run_trigger"), nullable=False)
    #: The attempt this row is: 1 for a run that was asked once, N for the N-th attempt of a
    #: scheduled run (ADR 0015). A manual/CLI run is always 1 and is never retried.
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    #: The row this one retries. Null on a first attempt; a retry is a new row created after the
    #: previous one is terminal, so the partial unique index is never violated (ADR 0014/0015).
    retry_of: Mapped[int | None] = mapped_column(
        ForeignKey("archive_worker_runs.id", ondelete="SET NULL"), nullable=True
    )
    #: The earliest moment this row may be claimed. Null means "now"; a retry carries the backoff's
    #: deadline computed from the database's clock, and the claim checks it (ADR 0015).
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    engine_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: The validated request this run was asked for (``engine_name``, ``preset``,
    #: ``db_batch_size``, ``options``, ``engine_options``). It is what makes a ``QUEUED`` row a work
    #: item the external runner can reproduce without the process that accepted it (ADR 0014). The
    #: runner resolves it again at claim and records the effective ``config``/``options``, so the
    #: queued row is the promise and the running row is the truth.
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)
    #: The **effective worker options** of the run (the columns it read, the floor it applied),
    #: resolved when the run started. ``config`` beside it is the engine's resolved configuration, so
    #: the row answers "with which model?" and "over which text?" without opening a hash (#120).
    #: Rows written before the column existed keep the empty default, and the panel says so.
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    #: The runner that claimed the row. Null while it is queued; set at claim, together with the
    #: lease. ``record_start``, ``heartbeat`` and ``finish`` are fenced by it, so a runner that lost
    #: its lease cannot close another runner's execution.
    runner_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Last sign of life from the claiming runner, written with the database's clock. The sweep
    #: only expires rows whose lease is older than ``now()``, so two machines never disagree about
    #: whether a runner is alive.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: When the claim expires if the runner stops renewing. A claim whose runner disappeared is
    #: marked ``INTERRUPTED`` by the next runner's sweep, never by the API's boot.
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: When the operator asked to stop this run. Null means nobody asked. This is a **request**, not
    #: a status: the row keeps ``QUEUED``/``RUNNING`` (and the slot) until the worker honours it at
    #: the next batch boundary, or until the API closes a never-claimed row at once.
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Who asked for the stop. A pair of its own, not a reuse of ``requested_by``: starting and
    #: stopping are two decisions, and the second may be taken by someone else. ``SET NULL`` for the
    #: account for the same reason as every other author link — the name survives the account.
    cancel_requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cancel_requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: The root cause, derived from ``error`` by ``archive_error_fingerprint``: the first line,
    #: lowercased, with ids, numbers and paths replaced by placeholders. A *generated* column and not
    #: a written one, deliberately — the backfill for the rows that already existed was the
    #: ``ALTER TABLE`` itself, so there is exactly one definition of the normalization and it cannot
    #: drift from the code that writes the message. Two runs of the same cause group; two causes with
    #: the same text do not, because ``error`` carries the exception's class.
    error_fingerprint: Mapped[str | None] = mapped_column(
        Text,
        Computed(WORKER_RUN_ERROR_FINGERPRINT_SQL, persisted=True),
        nullable=True,
    )

    __table_args__ = (
        # The concurrency guard, enforced by PostgreSQL: at most one run per worker may be in
        # flight, across processes and across a reload. A second submission becomes an
        # IntegrityError the API translates into a 409 with a sentence a person can read. It is
        # also the reason the queue is one slot per worker and not a backlog (ADR 0014).
        Index("uq_worker_run_active", "worker_name", unique=True, postgresql_where=text(ACTIVE_RUN_PREDICATE)),
        # The claim reads the oldest queued row; only queued rows are the queue, so the index is
        # partial and stays small no matter how long the ledger grows.
        Index("ix_worker_run_queue", "queued_at", postgresql_where=text(QUEUED_RUN_PREDICATE)),
        # The lease's two readers: the sweeper finds expired claims, and the runner's heartbeat
        # extends the claims it owns. Both only look at the rows in flight.
        Index("ix_worker_run_lease", "lease_expires_at", postgresql_where=text(RUNNING_RUN_PREDICATE)),
        Index("ix_worker_run_runner", "runner_id", postgresql_where=text(RUNNING_RUN_PREDICATE)),
        Index("ix_worker_run_queued_at", "queued_at"),
        # The grouped read of the failures screen. Without it the group-by would scan the ledger,
        # which is small today and is not a thing to rely on.
        Index("ix_worker_run_error_fingerprint", "error_fingerprint"),
        # The scheduler's "does this failed run already have a retry?" lookup (ADR 0015).
        Index("ix_worker_run_retry_of", "retry_of"),
    )


class WorkerSchedule(Base):
    """
    The agenda of one worker: a five-field cron in an explicit timezone and the request it runs.

    One row per worker (the primary key), because the queue is one slot per worker: two schedules for
    the same worker would only collide and be skipped (ADR 0015). ``request`` is the validated body
    the schedule was configured with, pinned here; the enqueue resolves the configuration from it and
    the persisted settings, so the parts the operator did not name still follow the settings.

    ``next_run_at`` is the scheduler's due check and survives a restart; ``last_enqueued_at`` and
    ``last_skipped_at`` are what let the panel say "ran at 02:00" and "skipped at 03:00 (a run was
    active)" without inventing a row. A disabled schedule has no ``next_run_at``: the toggle pauses,
    it does not delete, and turning it back on recomputes it from the cron.
    """

    __tablename__ = "archive_worker_schedules"

    worker_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    #: The five-field cron expression (``minute hour day-of-month month day-of-week``), evaluated in
    #: ``timezone``. The pair is validated at save time; the scheduler only trusts what it stored.
    cron: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The validated ``WorkerRunRequest`` (engine, preset, batch, options, engine options), pinned.
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: The account behind the name above; ``SET NULL`` for the same reason as the run's author.
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # The scheduler's due query: ``next_run_at <= now()`` over the enabled schedules.
        Index("ix_worker_schedule_next_run_at", "next_run_at"),
    )


class WorkerRunner(Base):
    """
    One runner process, as the operations panel sees it.

    The row is written at start-up (or refreshed with the same ``runner_id``) and renewed with the
    runner's own heartbeat. It is what lets the panel answer "is any runner alive?" and "can any of
    them run this worker?" without the API ever talking to a runner — the database is the only
    channel (ADR 0014).

    ``capabilities`` is the list of worker names the runner accepts (the ``--workers`` flag, or the
    whole catalogue). ``heartbeat_seconds`` is stored so the API can decide whether the runner is
    online from *its own* declared interval instead of a constant the runner cannot change. A
    stopped runner keeps its row: the ledger and the panel are allowed to remember it.
    """

    __tablename__ = "archive_worker_runners"

    runner_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The installed package version; ``NULL`` when the runner could not read its distribution.
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'::text[]")
    )
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    heartbeat_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=15, server_default=text("15"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The panel's only read: the runners whose heartbeat is recent enough to count as online.
        Index("ix_worker_runner_last_heartbeat", "last_heartbeat_at"),
    )


class ApiError(Base):
    """
    One unexpected HTTP failure, recorded so it can be grouped instead of only logged.

    It is its own table and not a row in ``archive_worker_runs``: that ledger is about a worker
    *execution*, and an HTTP request is not one — it has no queue, no concurrency guard and no
    resolved configuration. What the two share is the fingerprint, and that is what lets the failures
    screen show one root cause that broke both a worker and a request.

    Only **unexpected** failures land here. A missing document (404), a merge that cannot be undone
    (409) or a bad payload (422) are answers, not defects; recording them would bury the real ones
    under the ordinary noise of a form being filled in.

    ``request_id`` is the seam with the log: the same value is in the ``ui_stream.jsonl`` record of
    the request, so a row here leads to the traceback.
    """

    __tablename__ = "archive_api_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(400), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    #: Same function, same shape as the worker ledger's: one definition of "root cause" for both.
    error_fingerprint: Mapped[str | None] = mapped_column(
        Text,
        Computed("public.archive_error_fingerprint(message)", persisted=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_api_error_occurred_at", "occurred_at"),
        Index("ix_api_error_fingerprint", "error_fingerprint"),
    )
