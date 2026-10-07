"""Triggering a worker run from the panel, and reading the execution ledger.

The service resolves the configuration, writes the ``QUEUED`` row through the ledger's own committed
transaction and only then hands the id to the executor. That order is the whole design: the thread
marks the row as running from another session, so a row still inside the request's transaction would
be invisible to it and the run would sit at ``QUEUED`` forever.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import WorkerNotFoundError
from scrinalia.domains.archive.models.enums import WorkerRunStatus
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from scrinalia.domains.archive.schemas.system_schema import (
    WorkerRunDTO,
    WorkerRunListResponse,
    WorkerRunRequest,
)
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE
from scrinalia.domains.archive.workers.configuration import (
    ResolvedWorkerConfig,
    resolve_configuration,
    validate_engine_choice,
    validate_options,
)
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger


class WorkerRuntimePort(Protocol):
    """What the service needs from the executor: hand it a resolved run, do not wait for it."""

    def submit(self, worker_name: str, run_id: int, resolved: ResolvedWorkerConfig) -> None: ...


class WorkerRunService:
    """Queues a run and reads the ledger."""

    def __init__(self, db: Session, runtime: WorkerRuntimePort, ledger: WorkerRunLedger | None = None) -> None:
        self.db = db
        self.runtime = runtime
        self.ledger = ledger or WorkerRunLedger()
        self.runs = WorkerRunRepository(db)
        self.settings = WorkerSettingsRepository(db)

    def trigger(
        self, worker_name: str, request: WorkerRunRequest, *, requested_by: Author | None = None
    ) -> WorkerRunDTO:
        spec = WORKER_CATALOGUE.get(worker_name)
        if spec is None:
            raise WorkerNotFoundError(f"Worker '{worker_name}' não existe. Opções: {sorted(WORKER_CATALOGUE)}.")

        validate_engine_choice(spec, request.engine_name, request.preset)
        validate_options(spec, request.options)

        setting = self.settings.get(worker_name)
        resolved = resolve_configuration(
            self.db,
            spec,
            setting,
            engine_name=request.engine_name,
            preset=request.preset,
            db_batch_size=request.db_batch_size,
            options=request.options,
        )

        run = self.ledger.enqueue(
            worker_name,
            requested_by=requested_by,
            engine_name=resolved.engine_name,
            preset=resolved.preset,
            config=resolved.config,
        )
        self.runtime.submit(worker_name, run.run_id, resolved)
        return run

    def list_runs(
        self,
        *,
        worker_name: str | None,
        status: WorkerRunStatus | None,
        fingerprint: str | None = None,
        limit: int,
        offset: int,
    ) -> WorkerRunListResponse:
        items, total = self.runs.list(
            worker_name=worker_name, status=status, fingerprint=fingerprint, limit=limit, offset=offset
        )
        return WorkerRunListResponse(items=items, total=total, limit=limit, offset=offset)
