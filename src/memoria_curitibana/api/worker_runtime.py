"""Background executor for the worker runs triggered from the panel.

One AI worker at a time by default. The workers are CPU-bound (the ``Procfile`` runs the API with
``CUDA_VISIBLE_DEVICES=""``) and the pipeline has an order, so two torch models on the same CPU
would slow each other down without producing more. ``WORKER_RUNTIME_MAX_WORKERS`` widens it when the
deployment has the cores.

This is **not** a scheduler: no retry, no cron, no priority. It exists so the curator can press a
button, and the ledger is what makes the execution observable. Scaling the API to several processes
would require moving this executor out — the partial unique index still prevents two runs of the
same worker, but the start-up recovery would kill a sibling's live run.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from memoria_curitibana.core.config import settings
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from memoria_curitibana.domains.archive.workers.configuration import ResolvedWorkerConfig
from memoria_curitibana.domains.archive.workers.ledger import WorkerRunLedger


class WorkerRuntime:
    """Owns the thread pool and the ledger the runs write to."""

    def __init__(self, *, max_workers: int = 1, ledger: WorkerRunLedger | None = None) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="worker-run")
        self._ledger = ledger or WorkerRunLedger()

    def submit(self, worker_name: str, run_id: int, resolved: ResolvedWorkerConfig) -> None:
        """Hands a resolved run to the pool; the response does not wait for it."""
        self._executor.submit(self._execute, worker_name, run_id, resolved)

    def _execute(self, worker_name: str, run_id: int, resolved: ResolvedWorkerConfig) -> None:
        # Imported here, not at module level: importing the runner imports the nine worker modules
        # and, with them, spaCy and pandas. The API must not pay that at boot for a button nobody
        # has pressed yet.
        from memoria_curitibana.domains.archive.workers.runner import run_worker

        try:
            run_worker(
                worker_name,
                engine_name=resolved.engine_name,
                preset=resolved.preset,
                db_batch_size=resolved.db_batch_size,
                extra=resolved.forwarded_options,
                ledger=self._ledger,
                run_id=run_id,
                trigger=WorkerRunTrigger.API,
            )
        except Exception as exc:
            logger.exception(f"❌ A execução de '{worker_name}' disparada pelo painel falhou: {exc}")
            # The runner records its own failures; this covers the ones before it takes over
            # (opening the session, resolving the configuration), which would leave the row queued.
            self._ledger.finish(run_id, status=WorkerRunStatus.FAILED, error=str(exc))

    def shutdown(self, *, wait: bool = False) -> None:
        """Stops accepting work. A thread already running is not killed: the next boot marks it."""
        self._executor.shutdown(wait=wait, cancel_futures=True)


_runtime: WorkerRuntime | None = None
_runtime_lock = threading.Lock()


def provide_worker_runtime() -> WorkerRuntime:
    """Process-wide runtime, created on first use and replaced after a shutdown."""
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = WorkerRuntime(max_workers=settings.WORKER_RUNTIME_MAX_WORKERS)
    return _runtime


def shutdown_worker_runtime() -> None:
    """Drops the singleton so the next application (tests create several) gets a fresh pool."""
    global _runtime
    with _runtime_lock:
        runtime, _runtime = _runtime, None
    if runtime is not None:
        runtime.shutdown(wait=False)
