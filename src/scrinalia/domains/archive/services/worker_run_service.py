"""Triggering a worker run from the panel, and reading the execution ledger.

The service resolves the configuration, writes the ``QUEUED`` row through the ledger's own committed
transaction and returns it. That order is the whole design: the run is a queue item an external
runner claims (ADR 0014), so the row must be committed before the response and must carry the
request the runner will reproduce. The resolution here is the promise the panel shows; the runner
records the effective configuration when it starts.

There is no executor in this process. The API only enqueues; ``boot`` no longer repairs anything,
and the run's liveness is a lease the runner renews.

The cancellation follows the same rule (#72): this service writes the request and answers what it
did to the row, but it never stops a thread. A ``QUEUED`` row no runner claimed is closed at once;
an in-flight row is only *asked* to stop, and the worker honours the request at its next batch
boundary (ADR 0014 decision 9). The response distinguishes the two outcomes by code, because the
screen has two different sentences to show.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import (
    WorkerNotFoundError,
    WorkerRunNotCancellableError,
    WorkerRunNotFoundError,
)
from scrinalia.domains.archive.models.enums import ACTIVE_WORKER_RUN_STATUSES, WorkerRunStatus
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from scrinalia.domains.archive.schemas.responses import RouteMessageCode
from scrinalia.domains.archive.schemas.system_schema import (
    WorkerRunCancelResponse,
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
    """Queues and cancels a run, and reads the ledger."""

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

    def cancel(self, run_id: int, *, requested_by: Author | None = None) -> WorkerRunCancelResponse:
        """
        Asks one run to stop, and answers what the request did to the row.

        Two outcomes share the response shape because the screen says two different sentences. A
        ``QUEUED`` row no runner has claimed never started, so it is closed ``CANCELLED`` at once
        and its slot is free. A row in flight is only **asked**: the request is recorded with its
        author and the row keeps ``QUEUED``/``RUNNING`` (and the slot) until the worker honours it at
        the next batch boundary — releasing it while the worker still writes would let a second run
        overlap the first (ADR 0014 decision 9). The second request is idempotent, so a double click
        is not an error; a terminal row is a 409, because "there is nothing to cancel" is a fact
        the operator has to read, not a success the screen would have to explain away.
        """
        if self.runs.close_unclaimed(run_id, requested_by=requested_by):
            return self._cancel_answer(
                run_id,
                code=RouteMessageCode.WORKER_RUN_CANCELLED,
                message="Execução cancelada: ela ainda não havia sido reivindicada por um runner.",
            )
        if self.runs.request_cancel(run_id, requested_by=requested_by):
            return self._cancel_answer(
                run_id,
                code=RouteMessageCode.WORKER_RUN_CANCEL_REQUESTED,
                message="Cancelamento pedido: a execução para no fim do lote atual.",
            )

        run = self.runs.get(run_id, populate_existing=True)
        if run is None:
            raise WorkerRunNotFoundError(f"Execução {run_id} não existe no ledger.")
        if run.cancel_requested_at is not None and run.status in ACTIVE_WORKER_RUN_STATUSES:
            return WorkerRunCancelResponse(
                code=RouteMessageCode.WORKER_RUN_CANCEL_REQUESTED,
                message="O cancelamento desta execução já havia sido pedido; ela para no fim do lote atual.",
                data=run,
            )
        raise WorkerRunNotCancellableError(f"A execução {run_id} já terminou ({run.status}); não há o que cancelar.")

    def _cancel_answer(self, run_id: int, *, code: RouteMessageCode, message: str) -> WorkerRunCancelResponse:
        """The row as the write left it, re-read so the answer is not the state before the update."""
        run = self.runs.get(run_id, populate_existing=True)
        if run is None:
            raise WorkerRunNotFoundError(f"Execução {run_id} não existe no ledger.")
        return WorkerRunCancelResponse(code=code, message=message, data=run)

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
