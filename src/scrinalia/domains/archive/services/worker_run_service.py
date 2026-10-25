"""Triggering a worker run from the panel, and reading the execution ledger.

The service resolves the configuration, writes the ``QUEUED`` row through the ledger's own committed
transaction and returns it. That order is the whole design: the run is a queue item an external
runner claims (ADR 0014), so the row must be committed before the response and must carry the
request the runner will reproduce. The resolution here is the promise the panel shows; the runner
records the effective configuration when it starts.

There is no executor in this process. The API only enqueues; ``boot`` no longer repairs anything,
and the run's liveness is a lease the runner renews.
"""

from __future__ import annotations

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
    resolve_configuration,
    validate_engine_choice,
    validate_engine_options,
    validate_options,
)
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger


class WorkerRunService:
    """Queues a run and reads the ledger."""

    def __init__(self, db: Session, ledger: WorkerRunLedger | None = None) -> None:
        self.db = db
        self.ledger = ledger or WorkerRunLedger()
        self.runs = WorkerRunRepository(db)
        self.settings = WorkerSettingsRepository(db)

    def trigger(
        self, worker_name: str, request: WorkerRunRequest, *, requested_by: Author | None = None
    ) -> WorkerRunDTO:
        """
        Validates the request, resolves the configuration and enqueues the run.

        The response is the ``QUEUED`` row; a runner claims it when one is online. The explicitly
        named configuration is resolved here for the panel and frozen into ``config`` as the
        promise; the runner re-resolves it at claim under the same precedence and records the
        effective values (`record_start`), which is what keeps the active ``LLM_CHECK`` rule current.
        """
        spec = WORKER_CATALOGUE.get(worker_name)
        if spec is None:
            raise WorkerNotFoundError(f"Worker '{worker_name}' não existe. Opções: {sorted(WORKER_CATALOGUE)}.")

        validate_engine_choice(spec, request.engine_name, request.preset)
        validate_options(spec, request.options)
        validate_engine_options(spec, request.engine_options)

        setting = self.settings.get(worker_name)
        resolved = resolve_configuration(
            self.db,
            spec,
            setting,
            engine_name=request.engine_name,
            preset=request.preset,
            db_batch_size=request.db_batch_size,
            options=request.options,
            engine_options=request.engine_options,
        )

        return self.ledger.enqueue(
            worker_name,
            requested_by=requested_by,
            engine_name=resolved.engine_name,
            preset=resolved.preset,
            config=resolved.config,
            request=request.model_dump(mode="json"),
        )

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
