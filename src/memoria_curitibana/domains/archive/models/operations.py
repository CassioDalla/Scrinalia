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

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from memoria_curitibana.core.base import Base

from .enums import WorkerRunStatus, WorkerRunTrigger

#: Literal form of the partial index predicate. Kept next to the index so the model, the migration
#: and any hand-written query read the same words; ``ACTIVE_WORKER_RUN_STATUSES`` owns the meaning.
ACTIVE_RUN_PREDICATE = "status IN ('QUEUED', 'RUNNING')"

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
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WorkerRun(Base):
    """
    One execution of a worker, from the queue to the outcome.

    ``config`` is the **resolved** configuration (the preset already merged with the overrides), so
    the row keeps its meaning when a preset changes in code. ``error`` is the exception text,
    truncated: enough to act on, not a stack trace storage.
    """

    __tablename__ = "archive_worker_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[WorkerRunStatus] = mapped_column(
        Enum(WorkerRunStatus, name="worker_run_status"), nullable=False, index=True
    )
    trigger: Mapped[WorkerRunTrigger] = mapped_column(Enum(WorkerRunTrigger, name="worker_run_trigger"), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    engine_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=_EMPTY_JSON)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # The concurrency guard, enforced by PostgreSQL: at most one run per worker may be in
        # flight, across processes and across a reload. A second submission becomes an
        # IntegrityError the API translates into a 409 with a sentence a person can read.
        Index("uq_worker_run_active", "worker_name", unique=True, postgresql_where=text(ACTIVE_RUN_PREDICATE)),
        Index("ix_worker_run_queued_at", "queued_at"),
    )
