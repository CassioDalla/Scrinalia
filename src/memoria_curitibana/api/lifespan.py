"""Application lifespan: the background runtime and the recovery of interrupted runs.

A run row stuck at ``QUEUED``/``RUNNING`` is worse than a wrong one: the partial unique index would
block that worker forever. The start-up marks those rows as ``INTERRUPTED``, because they can only
belong to a process that is no longer alive — the same single-process assumption the executor makes.

The recovery is tolerant of a database that is offline: an operational convenience must never be the
reason the API refuses to boot.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from litestar import Litestar

from memoria_curitibana.api.worker_runtime import provide_worker_runtime, shutdown_worker_runtime
from memoria_curitibana.core.database import create_session
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.repository.worker_run_repo import WorkerRunRepository


def recover_interrupted_runs() -> int:
    """Marks the runs a dead process left in flight; returns how many were repaired."""
    try:
        with create_session() as db:
            recovered = WorkerRunRepository(db).recover_orphans()
            db.commit()
    except Exception as exc:
        logger.warning(f"⚠️ Não foi possível recuperar execuções interrompidas: {exc}")
        return 0

    if recovered:
        logger.warning(f"↩️ {recovered} execução(ões) de worker marcadas como interrompidas.")
    return recovered


@asynccontextmanager
async def application_lifespan(app: Litestar) -> AsyncIterator[None]:
    """Opens the executor, repairs the ledger and closes the pool on the way out."""
    recover_interrupted_runs()
    provide_worker_runtime()
    try:
        yield
    finally:
        shutdown_worker_runtime()
