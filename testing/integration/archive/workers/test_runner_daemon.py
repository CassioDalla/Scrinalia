"""The runner process: claim, execute, close, register and refuse a lost lease (ADR 0014)."""

import pytest
from sqlalchemy import delete, func, update
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.models.operations import WorkerRun, WorkerRunner
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.workers import runner
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger
from scrinalia.domains.archive.workers.runner import WorkerRunLeaseLostError
from scrinalia.domains.archive.workers.runner_daemon import RunnerConfig, RunnerService


def _queued(engine, worker_name: str = "cleaning") -> int:
    with Session(bind=engine) as db:
        run = WorkerRunRepository(db).create_queued(
            worker_name,
            trigger=WorkerRunTrigger.API,
            requested_by=None,
            engine_name=None,
            preset=None,
            config={},
        )
        db.commit()
        return run.run_id


def _cleanup(engine, *, run_id: int | None, runner_id: str) -> None:
    with Session(bind=engine) as db:
        if run_id is not None:
            db.execute(delete(WorkerRun).where(WorkerRun.id == run_id))
        db.execute(delete(WorkerRunner).where(WorkerRunner.runner_id == runner_id))
        db.commit()


def _config(runner_id: str = "runner-test") -> RunnerConfig:
    return RunnerConfig(
        runner_id=runner_id,
        name="test",
        capabilities=("cleaning",),
        once=True,
        heartbeat_seconds=5,
        lease_seconds=60,
        poll_seconds=0.1,
        sweep_seconds=0.1,
    )


def test_once_claims_executes_and_closes_one_run(engine, monkeypatch) -> None:
    seen: list[bool] = []

    def fake_cleaning(db, **kwargs) -> None:
        seen.append(True)

    monkeypatch.setitem(runner.WORKERS, "cleaning", fake_cleaning)

    run_id = _queued(engine)
    runner_id = "runner-test"
    try:
        RunnerService(_config(runner_id), session_factory=lambda: Session(bind=engine)).run()

        with Session(bind=engine) as db:
            stored = WorkerRunRepository(db).get(run_id)
            registered = db.get(WorkerRunner, runner_id)

        assert seen == [True]
        assert stored is not None
        assert stored.status == WorkerRunStatus.SUCCESS
        assert stored.runner_id == runner_id
        assert stored.started_at is not None
        assert registered is not None
        assert registered.stopped_at is not None
        assert registered.capabilities == ["cleaning"]
    finally:
        _cleanup(engine, run_id=run_id, runner_id=runner_id)


def test_a_run_whose_lease_was_swept_is_not_executed(engine, monkeypatch) -> None:
    seen: list[bool] = []

    def fake_cleaning(db, **kwargs) -> None:
        seen.append(True)

    monkeypatch.setitem(runner.WORKERS, "cleaning", fake_cleaning)

    run_id = _queued(engine)
    runner_id = "runner-a"

    def sessions() -> Session:
        return Session(bind=engine)

    ledger = WorkerRunLedger(session_factory=sessions)
    claimed = ledger.claim(["cleaning"], runner_id=runner_id, lease_seconds=60)
    assert claimed is not None

    with Session(bind=engine) as db:
        db.execute(
            update(WorkerRun)
            .where(WorkerRun.id == run_id)
            .values(lease_expires_at=func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 1))
        )
        db.commit()
    assert ledger.expire_stale_leases() == 1

    try:
        with pytest.raises(WorkerRunLeaseLostError):
            runner.run_worker(
                "cleaning",
                db_factory=sessions,
                ledger=ledger,
                run_id=run_id,
                runner_id=runner_id,
                lease_seconds=60,
            )
        assert seen == []
    finally:
        _cleanup(engine, run_id=run_id, runner_id=runner_id)
