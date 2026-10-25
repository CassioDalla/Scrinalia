"""The execution ledger writer used by the runner, the CLI and the panel's trigger.

The ledger lives in its own short-lived session, never in the worker's and never in the request's:
a worker commits and rolls back per batch, and an entry that vanished with a rollback would be worse
than no ledger at all. It is also what makes the API's trigger race-free — the ``QUEUED`` row is
committed before any runner can claim it, so a claim always finds it.

Since ADR 0014 the same object also carries the queue operations the runner and the CLI use:
``claim`` (the oldest row this runner accepts), ``record_start`` (the configuration it resolved),
``heartbeat`` (the lease), ``expire_stale_leases`` (the orphan recovery that left the API),
``finish`` (fenced by the runner that claimed the row) and, since #72, ``cancel_requested`` (the read
the worker repeats at every batch boundary).

The failure modes are treated differently on purpose:

* A **concurrency conflict** (the partial unique index) is raised: it means another run of the same
  worker is in flight, and the caller must not start a second one.
* A **claim** failure is raised: the runner decides whether to retry, and a silent empty claim would
  look like an empty queue.
* Any **other** ledger failure is logged and swallowed. A bookkeeping table must never be the reason
  a worker cannot run, and a failed heartbeat is a lease that will expire, not an exception in the
  middle of a run.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.exc import IntegrityError

from scrinalia.core.author import Author
from scrinalia.core.database import SessionFactory, create_session
from scrinalia.core.logger import logger
from scrinalia.domains.archive.exceptions import WorkerRunAlreadyActiveError
from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.repository.worker_run_repo import ClaimedRun, WorkerRunRepository
from scrinalia.domains.archive.schemas.system_schema import WorkerRunDTO
from scrinalia.metadata import load_all_models


class WorkerRunLedger:
    """Writes one line per execution, with its own transaction."""

    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        # The row carries a foreign key into ``auth_users``, and SQLAlchemy resolves a foreign key
        # when it flushes the insert. A process that imported only the archive models (the CLI did)
        # could not open the ledger at all, and the ledger swallows a bookkeeping failure by design:
        # the run happened and left no line. Loading the model packages here makes the guarantee the
        # ledger's own instead of the caller's.
        load_all_models()
        self._session_factory = session_factory

    def enqueue(
        self,
        worker_name: str,
        *,
        requested_by: Author | None,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
        request: dict[str, Any] | None = None,
    ) -> WorkerRunDTO:
        """
        Creates the ``QUEUED`` row and commits it before returning.

        The commit is the point: a runner opens its own session to claim the row, and a row still
        inside the request's uncommitted transaction would be invisible to it — the run would sit at
        ``QUEUED`` forever. ``request`` is the validated body that lets the runner reproduce the
        execution without this process (ADR 0014).
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
                    request=request,
                )
                db.commit()
                return run
        except IntegrityError as exc:
            raise WorkerRunAlreadyActiveError(
                f"Já existe uma execução em andamento para o worker '{worker_name}'."
            ) from exc

    def claim(self, worker_names: Sequence[str], *, runner_id: str, lease_seconds: int) -> ClaimedRun | None:
        """
        Claims the oldest queued run this runner advertises, and commits the claim.

        The commit is what makes the claim visible to the panel and to the heartbeat: the row is
        ``RUNNING`` with a lease before the worker starts. A database failure is raised, not
        swallowed — the runner must not mistake an unreachable database for an empty queue.
        """
        with self._session_factory() as db:
            run = WorkerRunRepository(db).claim_next(worker_names, runner_id=runner_id, lease_seconds=lease_seconds)
            db.commit()
            return run

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
        Records the effective configuration of a claimed run, fenced to its runner.

        ``False`` means the lease was swept between the claim and the resolution: the caller must
        not execute a run it no longer owns. The commit is deliberate — the row must be readable by
        the panel while the worker is already running.
        """
        with self._session_factory() as db:
            recorded = WorkerRunRepository(db).record_start(
                run_id,
                runner_id=runner_id,
                engine_name=engine_name,
                preset=preset,
                config=config,
                options=options,
            )
            db.commit()
            if not recorded:
                logger.warning(
                    f"⚠️ A execução {run_id} já não pertence ao runner '{runner_id}': o lease venceu "
                    "antes do início e o resultado não será executado."
                )
            return recorded

    def heartbeat(self, runner_id: str, *, lease_seconds: int, run_ids: Sequence[int] | None = None) -> int:
        """
        Renews the lease of the runs this runner owns; never raises.

        A failed heartbeat is a lease that will expire — the next sweep will mark the run
        ``INTERRUPTED`` — not a reason to kill the worker. The run's own database writes fail when
        the database is down, which is the case this path cannot repair.
        """
        try:
            with self._session_factory() as db:
                renewed = WorkerRunRepository(db).heartbeat(runner_id, lease_seconds=lease_seconds, run_ids=run_ids)
                db.commit()
                return renewed
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível renovar o lease do runner '{runner_id}': {exc}")
            return 0

    def expire_stale_leases(self) -> int:
        """
        Marks the claims whose lease expired as ``INTERRUPTED``; never raises.

        Called by the runner and by the CLI at start-up, so a crashed process is repaired by the
        next one instead of by the API's boot.
        """
        try:
            with self._session_factory() as db:
                expired = WorkerRunRepository(db).expire_stale_leases()
                db.commit()
                if expired:
                    logger.warning(
                        f"↩️ {expired} execução(ões) de worker com lease vencido marcadas como interrompidas."
                    )
                return expired
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível varrer os leases vencidos: {exc}")
            return 0

    def cancel_requested(self, run_id: int) -> bool:
        """
        Whether the operator asked this run to stop; never raises.

        The worker consults this once per batch (``RunControl.checkpoint``). A ledger that cannot be
        read must not kill a run that is otherwise healthy: the answer is "not requested", and the
        same failure that hid the read will show up on the panel as a stale run — the honest place
        for it, not the middle of a batch.
        """
        try:
            with self._session_factory() as db:
                return WorkerRunRepository(db).is_cancel_requested(run_id)
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível ler o pedido de cancelamento da execução {run_id}: {exc}")
            return False

    def start(
        self,
        worker_name: str,
        *,
        trigger: WorkerRunTrigger,
        requested_by: Author | None,
        engine_name: str | None,
        preset: str | None,
        config: dict[str, Any],
        request: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        runner_id: str | None = None,
        lease_seconds: int | None = None,
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
                    request=request,
                    options=options,
                    runner_id=runner_id,
                    lease_seconds=lease_seconds,
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

    def finish(
        self,
        run_id: int,
        *,
        status: WorkerRunStatus,
        error: str | None = None,
        error_kind: str | None = None,
        runner_id: str | None = None,
    ) -> bool:
        """
        Closes the run with its outcome; never raises.

        ``False`` means the row was not closed — the runner lost its lease, or the row was already
        terminal — and the caller does not pretend the outcome was recorded. The archive writes the
        worker made are still in the database and its stamps still say what it processed.
        """
        try:
            with self._session_factory() as db:
                closed = WorkerRunRepository(db).finish(
                    run_id, status=status, error=error, error_kind=error_kind, runner_id=runner_id
                )
                db.commit()
                if not closed:
                    logger.warning(
                        f"⚠️ A execução {run_id} já não estava em andamento sob o runner "
                        f"'{runner_id or '—'}': o resultado não foi gravado na linha."
                    )
                return closed
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível fechar o registro da execução {run_id}: {exc}")
            return False
