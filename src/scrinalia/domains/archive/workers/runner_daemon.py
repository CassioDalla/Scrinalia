"""The external runner: the process that drains the run queue.

ADR 0014 moves the executor out of the API. This process claims ``QUEUED`` rows from
``archive_worker_runs`` with ``FOR UPDATE SKIP LOCKED``, runs the worker on the machine that has the
models, and renews a lease while it does. It talks to the database and to nothing else: the API never
calls it, and the panel learns what it is doing by reading the same ledger.

``--workers`` narrows the workers this runner accepts (the default is the whole catalogue), so a GPU
host can serve the model-backed workers while another runner serves the cheap ones. The database is
the scheduler: a second runner skips a row another one is claiming, and the partial unique index
keeps at most one run per worker in flight.

The runner refuses to start against a schema behind its code (two machines, one release) and records
its package version in ``archive_worker_runners`` so the panel can show a mismatch.
"""

from __future__ import annotations

import argparse
import signal
import socket
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import uuid4

from scrinalia.core.cli import positive_int
from scrinalia.core.database import SessionFactory, create_runner_session
from scrinalia.core.logger import logger
from scrinalia.domains.archive.models.enums import WorkerRunStatus
from scrinalia.domains.archive.repository.worker_run_repo import ClaimedRun
from scrinalia.domains.archive.repository.worker_runner_repo import WorkerRunnerRepository
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE
from scrinalia.domains.archive.workers.lease import RunLeaseMonitor
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger
from scrinalia.domains.archive.workers.runner import run_worker
from scrinalia.domains.archive.workers.schema import assert_schema_at_head


@dataclass(frozen=True)
class RunnerConfig:
    """What one runner process is: its identity, its capabilities and its timings."""

    runner_id: str
    name: str
    capabilities: tuple[str, ...]
    concurrency: int = 1
    heartbeat_seconds: int = 15
    lease_seconds: int = 60
    poll_seconds: float = 2.0
    sweep_seconds: float = 30.0
    once: bool = False
    drain_seconds: int = 0


def _package_version() -> str | None:
    """The installed package version, or ``None`` when the runner is not installed as a package."""
    try:
        return version("scrinalia")
    except PackageNotFoundError:
        return None


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class RunnerService:
    """The claim loop, the pool and the lease monitor of one runner."""

    def __init__(
        self,
        config: RunnerConfig,
        *,
        session_factory: SessionFactory = create_runner_session,
        ledger: WorkerRunLedger | None = None,
    ) -> None:
        self.config = config
        self._session_factory = session_factory
        self._ledger = ledger or WorkerRunLedger(session_factory=session_factory)
        self._monitor = RunLeaseMonitor(
            config.runner_id,
            lease_seconds=config.lease_seconds,
            interval_seconds=config.heartbeat_seconds,
            session_factory=session_factory,
            ledger=self._ledger,
            heartbeat_runner=True,
        )
        self._stop = threading.Event()
        self._active: set[Future[None]] = set()
        self._pool = ThreadPoolExecutor(max_workers=config.concurrency, thread_name_prefix="runner-run")

    def stop(self) -> None:
        """Stops claiming; the in-flight runs finish (or are left to the lease)."""
        self._stop.set()

    def run(self) -> None:
        """Sweeps the stale claims, registers, and serves until ``--once`` or a stop signal."""
        self._ledger.expire_stale_leases()
        self._register()
        self._monitor.start()
        try:
            if self.config.once:
                self._run_once()
            else:
                self._loop()
        finally:
            self._shutdown()

    def _run_once(self) -> None:
        claimed = self._claim()
        if claimed is None:
            logger.info("No queued run for this runner; exiting (--once).")
            return
        self._execute(claimed)

    def _loop(self) -> None:
        last_sweep = time.monotonic()
        while not self._stop.is_set():
            self._prune()
            if len(self._active) < self.config.concurrency:
                claimed = self._claim()
                if claimed is not None:
                    self._active.add(self._pool.submit(self._execute, claimed))
                    continue
            if time.monotonic() - last_sweep >= self.config.sweep_seconds:
                self._ledger.expire_stale_leases()
                last_sweep = time.monotonic()
            self._stop.wait(self.config.poll_seconds)

    def _prune(self) -> None:
        self._active = {future for future in self._active if not future.done()}

    def _claim(self) -> ClaimedRun | None:
        try:
            return self._ledger.claim(
                list(self.config.capabilities),
                runner_id=self.config.runner_id,
                lease_seconds=self.config.lease_seconds,
            )
        except Exception as exc:
            logger.error(f"⚠️ Could not claim a run: {exc}")
            return None

    def _execute(self, claimed: ClaimedRun) -> None:
        try:
            run_worker(
                claimed.worker_name,
                engine_name=_optional_str(claimed.request.get("engine_name")),
                preset=_optional_str(claimed.request.get("preset")),
                db_batch_size=_optional_int(claimed.request.get("db_batch_size")),
                origin_code=claimed.origin_code,
                extra=_optional_dict(claimed.request.get("options")),
                engine_options=_optional_dict(claimed.request.get("engine_options")),
                db_factory=self._session_factory,
                ledger=self._ledger,
                run_id=claimed.run_id,
                runner_id=self.config.runner_id,
                lease_seconds=self.config.lease_seconds,
                lease_monitor=self._monitor,
            )
        except Exception as exc:
            logger.exception(f"❌ The run {claimed.run_id} of '{claimed.worker_name}' failed: {exc}")
            # The runner records its own failures; this covers the ones before ``run_worker`` takes
            # over (resolving the request, opening the session), which would leave the row RUNNING.
            self._ledger.finish(
                claimed.run_id,
                status=WorkerRunStatus.FAILED,
                error=str(exc),
                error_kind=type(exc).__name__,
                runner_id=self.config.runner_id,
            )

    def _register(self) -> None:
        with self._session_factory() as db:
            WorkerRunnerRepository(db).register(
                self.config.runner_id,
                name=self.config.name,
                hostname=socket.gethostname(),
                version=_package_version(),
                capabilities=list(self.config.capabilities),
                concurrency=self.config.concurrency,
                heartbeat_seconds=self.config.heartbeat_seconds,
            )
            db.commit()

    def _stop_registry(self) -> None:
        try:
            with self._session_factory() as db:
                WorkerRunnerRepository(db).stop(self.config.runner_id)
                db.commit()
        except Exception as exc:
            logger.error(f"⚠️ Could not mark the runner '{self.config.runner_id}' as stopped: {exc}")

    def _shutdown(self) -> None:
        if self.config.drain_seconds > 0 and self._active:
            wait(self._active, timeout=self.config.drain_seconds)
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._monitor.stop()
        self._stop_registry()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute the archive AI workers from the run queue (ADR 0014).",
    )
    parser.add_argument("--name", default=socket.gethostname(), help="Human name of this runner.")
    parser.add_argument("--id", dest="runner_id", default=None, help="Stable identifier; generated by default.")
    parser.add_argument(
        "--workers",
        default="",
        help="Comma-separated worker names this runner accepts; the default is the whole catalogue.",
    )
    parser.add_argument("--concurrency", type=positive_int, default=1, help="Runs executed at once.")
    parser.add_argument("--heartbeat-seconds", type=positive_int, default=15, help="How often the lease is renewed.")
    parser.add_argument(
        "--lease-seconds", type=positive_int, default=60, help="How long a claim lives without a heartbeat."
    )
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Idle polling interval.")
    parser.add_argument(
        "--sweep-seconds", type=float, default=30.0, help="How often expired claims are marked interrupted."
    )
    parser.add_argument("--once", action="store_true", help="Claim and run at most one execution, then exit.")
    parser.add_argument(
        "--drain-seconds",
        type=positive_int,
        default=0,
        help="Wait up to this many seconds for in-flight runs before exiting; the lease covers the rest.",
    )
    return parser.parse_args(argv)


def _build_config(args: argparse.Namespace) -> RunnerConfig:
    """Validates the command line into a config; a typo is refused before the first claim."""
    names = tuple(part.strip() for part in str(args.workers).split(",") if part.strip())
    capabilities = names or tuple(WORKER_CATALOGUE)
    unknown = sorted(set(capabilities) - set(WORKER_CATALOGUE))
    if unknown:
        raise SystemExit(f"Unknown worker(s): {unknown}. Known workers: {sorted(WORKER_CATALOGUE)}.")
    if args.heartbeat_seconds >= args.lease_seconds:
        raise SystemExit("--heartbeat-seconds must be smaller than --lease-seconds.")
    if args.poll_seconds <= 0:
        raise SystemExit("--poll-seconds must be positive.")
    if args.sweep_seconds <= 0:
        raise SystemExit("--sweep-seconds must be positive.")

    return RunnerConfig(
        runner_id=args.runner_id or f"{args.name}:{uuid4().hex[:8]}",
        name=args.name,
        capabilities=capabilities,
        concurrency=args.concurrency,
        heartbeat_seconds=args.heartbeat_seconds,
        lease_seconds=args.lease_seconds,
        poll_seconds=args.poll_seconds,
        sweep_seconds=args.sweep_seconds,
        once=args.once,
        drain_seconds=args.drain_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    config = _build_config(_parse_args(argv))
    assert_schema_at_head()
    service = RunnerService(config)
    signal.signal(signal.SIGTERM, lambda *_: service.stop())
    signal.signal(signal.SIGINT, lambda *_: service.stop())
    logger.info(
        f"🏃 Runner '{config.runner_id}' serving {len(config.capabilities)} worker(s) "
        f"with concurrency {config.concurrency}."
    )
    service.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
