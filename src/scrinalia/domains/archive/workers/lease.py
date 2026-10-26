"""The lease monitor: the thread that proves a runner (or a CLI run) is still alive.

ADR 0014 makes ``heartbeat_at``/``lease_expires_at`` the only liveness proof, and every timestamp is
PostgreSQL's ``now()``: the runner and the database are different machines, so the runner's clock
cannot be the proof. This thread renews two things:

* the runs it tracks, through the ledger's own committed session, so a finished run is never
  extended;
* the runner's own row in ``archive_worker_runners``, when it is a daemon — the CLI is a one-shot
  runner with no registry row.

A failed beat is logged and retried; the lease is what expires, not the worker. The run's own
database writes fail when the database is down, which is the case this thread cannot repair.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Protocol

from scrinalia.core.database import SessionFactory, create_session
from scrinalia.core.logger import logger
from scrinalia.domains.archive.repository.worker_runner_repo import WorkerRunnerRepository
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger


class LeaseWriter(Protocol):
    """What the monitor needs from the ledger: renew the lease of the runs it owns."""

    def heartbeat(self, runner_id: str, *, lease_seconds: int, run_ids: Sequence[int] | None = None) -> int:
        raise NotImplementedError


class RunLeaseMonitor:
    """Renews the lease of the runs a runner owns, and the runner's own row."""

    def __init__(
        self,
        runner_id: str,
        *,
        lease_seconds: int,
        interval_seconds: int,
        session_factory: SessionFactory = create_session,
        ledger: LeaseWriter | None = None,
        heartbeat_runner: bool = True,
    ) -> None:
        if interval_seconds >= lease_seconds:
            raise ValueError("the heartbeat interval must be smaller than the lease it renews")
        self._runner_id = runner_id
        self._lease_seconds = lease_seconds
        self._interval = interval_seconds
        self._session_factory = session_factory
        self._ledger = ledger or WorkerRunLedger(session_factory=session_factory)
        self._heartbeat_runner = heartbeat_runner
        self._tracked: set[int] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Starts the daemon thread; idempotent."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"lease-{self._runner_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops the thread and waits briefly for the current beat; idempotent."""
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)

    def track(self, run_id: int) -> None:
        """Starts renewing one run; the caller commits the claim before calling this."""
        with self._lock:
            self._tracked.add(run_id)

    def release(self, run_id: int) -> None:
        """Stops renewing one run; called in the ``finally`` of every execution."""
        with self._lock:
            self._tracked.discard(run_id)

    def beat_now(self) -> None:
        """One beat, exposed for tests and for the first renewal after a restart."""
        self._beat()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._beat()

    def _beat(self) -> None:
        with self._lock:
            run_ids = sorted(self._tracked)
        # An empty set means "renew every RUNNING row this runner owns": after a restart the
        # monitor may not have tracked a claim yet, and renewing a run twice is harmless.
        self._ledger.heartbeat(self._runner_id, lease_seconds=self._lease_seconds, run_ids=run_ids or None)
        if not self._heartbeat_runner:
            return
        try:
            with self._session_factory() as db:
                WorkerRunnerRepository(db).heartbeat(self._runner_id)
                db.commit()
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível renovar o registro do runner '{self._runner_id}': {exc}")
