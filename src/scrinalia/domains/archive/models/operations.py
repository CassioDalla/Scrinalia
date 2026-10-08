"""Operational state of the AI workers: persisted defaults and the execution ledger.

Two concerns live here, both owned by the *operation* of the system rather than by the archival
record:

* ``WorkerSetting`` — the default engine/preset/batch/options of a worker, which the runner uses
  when the command line says nothing. ``WorkerSettingRevision`` is its audit trail, in the same
  spirit as ``ArchiveDocumentRevision``: the decision and the write are different facts.
* ``WorkerRun`` — one line per execution, written by the runner for **both** the CLI and the panel,
  so the ledger is about the worker and not about the button that started it.

There is deliberately **no foreign key to a worker table**: workers are code, not rows. A run whose
worker was later removed from the catalogue stays readable, which is what a ledger is for.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Computed, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base

from .enums import WorkerRunStatus, WorkerRunTrigger

#: Literal form of the partial index predicate. Kept next to the index so the model, the migration
#: and any hand-written query read the same words; ``ACTIVE_WORKER_RUN_STATUSES`` owns the meaning.
ACTIVE_RUN_PREDICATE = "status IN ('QUEUED', 'RUNNING')"

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

    ``config`` is the **resolved** configuration (the preset already merged with the overrides), so
    the row keeps its meaning when a preset changes in code. ``error`` is the exception text,
    prefixed with its class (``ValueError: ...``) and truncated: enough to act on, not a stack trace
    storage. ``error_fingerprint`` is the *root cause* of that text, computed by PostgreSQL — see
    the column below.
    """

    __tablename__ = "archive_worker_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[WorkerRunStatus] = mapped_column(
        Enum(WorkerRunStatus, name="worker_run_status"), nullable=False, index=True
    )
    trigger: Mapped[WorkerRunTrigger] = mapped_column(Enum(WorkerRunTrigger, name="worker_run_trigger"), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: The account behind the name above. ``SET NULL`` and not ``CASCADE``: an account is deactivated, never deleted,
    #: and if one ever were, the decision it took must survive with its author's name.
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    engine_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        # IntegrityError the API translates into a 409 with a sentence a person can read.
        Index("uq_worker_run_active", "worker_name", unique=True, postgresql_where=text(ACTIVE_RUN_PREDICATE)),
        Index("ix_worker_run_queued_at", "queued_at"),
        # The grouped read of the failures screen. Without it the group-by would scan the ledger,
        # which is small today and is not a thing to rely on.
        Index("ix_worker_run_error_fingerprint", "error_fingerprint"),
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
