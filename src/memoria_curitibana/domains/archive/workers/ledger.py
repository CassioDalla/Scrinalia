"""The execution ledger writer used by the runner and by the panel's trigger.

The ledger lives in its own short-lived session, never in the worker's and never in the request's:
a worker commits and rolls back per batch, and an entry that vanished with a rollback would be worse
than no ledger at all. It is also what makes the API's trigger race-free — the ``QUEUED`` row is
committed before the executor thread is handed the id, so the thread always finds it.

The two failure modes are treated differently on purpose:

* A **concurrency conflict** (the partial unique index) is raised: it means another run of the same
  worker is in flight, and the caller must not start a second one.
* Any **other** ledger failure is logged and swallowed. A bookkeeping table must never be the
  reason a worker cannot run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from memoria_curitibana.core.database import create_session
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.exceptions import WorkerRunAlreadyActiveError
from memoria_curitibana.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from memoria_curitibana.domains.archive.repository.worker_run_repo import WorkerRunRepository
from memoria_curitibana.domains.archive.schemas.system_schema import WorkerRunDTO


class SessionContext(Protocol):
    """A session that can be opened with ``with`` — what ``create_session`` and a test double share."""

    def __enter__(self) -> Session: ...

    def __exit__(self, type_: Any, value: Any, traceback: Any) -> None: ...


SessionFactory = Callable[[], SessionContext]


class WorkerRunLedger:
    """Writes one line per execution, with its own transaction."""

    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def enqueue(
        self,
        worker_name: str,
        *,
        requested_by: str | None,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
    ) -> WorkerRunDTO:
        """
        Creates the ``QUEUED`` row and commits it before returning.

        The commit is the point: the executor thread opens its own session to mark the row as
        running, and a row still inside the request's uncommitted transaction would be invisible to
        it — the run would sit at ``QUEUED`` forever.
        """
        try:
            with self._session_factory() as db:
                run = WorkerRunRepository(db).create_queued(
                    worker_name,
                    trigger=WorkerRunTrigger.API,
                    requested_by=requested_by,
                    engine_name=engine_name,
                    preset=preset,
                    config=config,
                )
                db.commit()
                return run
        except IntegrityError as exc:
            raise WorkerRunAlreadyActiveError(
                f"Já existe uma execução em andamento para o worker '{worker_name}'."
            ) from exc

    def start(
        self,
        worker_name: str,
        *,
        trigger: WorkerRunTrigger,
        requested_by: str | None,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
    ) -> int | None:
        """Opens a run that is already executing. Returns its id, or ``None`` if the ledger failed."""
        try:
            with self._session_factory() as db:
                run = WorkerRunRepository(db).create_running(
                    worker_name,
                    trigger=trigger,
                    requested_by=requested_by,
                    engine_name=engine_name,
                    preset=preset,
                    config=config,
                )
                db.commit()
                return run.run_id
        except IntegrityError as exc:
            raise WorkerRunAlreadyActiveError(
                f"Já existe uma execução em andamento para o worker '{worker_name}'."
            ) from exc
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível abrir o registro da execução de '{worker_name}': {exc}")
            return None

    def mark_running(self, run_id: int) -> None:
        """Moves a queued row to running, which is when the executor's thread really starts."""
        try:
            with self._session_factory() as db:
                WorkerRunRepository(db).mark_running(run_id)
                db.commit()
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível marcar a execução {run_id} como em andamento: {exc}")

    def finish(self, run_id: int, *, status: WorkerRunStatus, error: str | None = None) -> None:
        """Closes the run with its outcome; never raises."""
        try:
            with self._session_factory() as db:
                WorkerRunRepository(db).finish(run_id, status=status, error=error)
                db.commit()
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível fechar o registro da execução {run_id}: {exc}")
