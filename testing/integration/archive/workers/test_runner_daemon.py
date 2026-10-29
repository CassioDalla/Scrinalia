"""The runner process: claim, execute, close, register and refuse a lost lease (ADR 0014)."""

import pytest
from sqlalchemy import delete, func, update
from sqlalchemy.orm import Session

from scrinalia.domains.archive.evaluation import trial as trial_module
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveTypology
from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.models.operations import WorkerRun, WorkerRunner
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.schemas.system_schema import WorkerRunRequest, WorkerTrialRequest
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


def _config(runner_id: str = "runner-test", *, capabilities: tuple[str, ...] = ("cleaning",)) -> RunnerConfig:
    return RunnerConfig(
        runner_id=runner_id,
        name="test",
        capabilities=capabilities,
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


class _FakeTypology:
    """A classifier that always answers the first active label, so the wiring is what is tested."""

    def classify(self, texts, labels, batch_size=1):
        return [{"labels": [labels[0]], "scores": [0.9]} for _ in texts]


def test_the_daemon_dispatches_a_trial_and_records_its_result(engine, monkeypatch) -> None:
    """
    The claim knows the row is a trial and the executor owns the close (ADR 0018).

    The production path must not run for a trial — it would classify and stamp the collection — and
    the result has to be on the row before the runner releases the lease. The model is faked: what
    this pins is the dispatch, the ledger write and the absence of archival writes.
    """
    monkeypatch.setattr(trial_module, "_build_engine", lambda _resolved: _FakeTypology())
    runner_id = "runner-trial"
    description_ids = ["trial-doc-1", "trial-doc-2"]
    with Session(bind=engine) as db:
        db.add(ArchiveTypology(typology_id=990, name="Fotografia", is_active=True))
        for description_id in description_ids:
            db.add(
                ArchiveDocument(
                    description_id=description_id,
                    original_title="Foto da praça",
                    staging_content_hash="hash-trial",
                )
            )
        request = WorkerTrialRequest(
            sample=5,
            seed="daemon-seed",
            configs=[
                WorkerRunRequest(engine_name="deberta_typology", preset="cpu_local"),
                WorkerRunRequest(engine_name="deberta_typology", preset="cpu_local"),
            ],
        )
        run = WorkerRunRepository(db).create_queued(
            "typology",
            trigger=WorkerRunTrigger.API,
            requested_by=None,
            engine_name=None,
            preset=None,
            config={},
            request=request.model_dump(mode="json"),
            trial=True,
        )
        run_id = run.run_id
        db.commit()

    config = RunnerConfig(
        runner_id=runner_id,
        name="test",
        capabilities=("typology",),
        once=True,
        heartbeat_seconds=5,
        lease_seconds=60,
        poll_seconds=0.1,
        sweep_seconds=0.1,
    )
    try:
        RunnerService(config, session_factory=lambda: Session(bind=engine)).run()

        with Session(bind=engine) as db:
            stored = db.get(WorkerRun, run_id)
            docs = [db.get(ArchiveDocument, description_id) for description_id in description_ids]
            assert stored is not None
            assert stored.status == WorkerRunStatus.SUCCESS
            assert stored.trial is True
            assert stored.trial_result is not None
            assert len(stored.trial_result["configs"]) == 2
            assert stored.trial_result["sample"]["seed"] == "daemon-seed"
            assert stored.trial_result["configs"][0]["processed"] == 2
            for doc in docs:
                assert doc is not None
                assert doc.typology_id is None, "the trial must not classify the sample"
                assert not doc.execution_log, "the trial must not stamp the sample"
    finally:
        with Session(bind=engine) as db:
            db.execute(delete(ArchiveDocument).where(ArchiveDocument.description_id.in_(description_ids)))
            db.execute(delete(ArchiveTypology).where(ArchiveTypology.typology_id == 990))
            db.commit()
        _cleanup(engine, run_id=run_id, runner_id=runner_id)


def test_a_diffusion_run_is_dispatched_with_the_channel(engine, monkeypatch) -> None:
    """The channel is the run's axis: it reaches the worker, and the adapter receives the row."""
    from scrinalia.domains.diffusion.diffusion_registry import CHANNELS
    from scrinalia.domains.diffusion.models import DiffusionChannel
    from scrinalia.domains.diffusion.repository import DiffusionChannelRepository
    from testing.integration.diffusion import fake_adapter
    from testing.integration.diffusion.fake_channel import FAKE_EXPORT

    monkeypatch.setitem(CHANNELS, "fake_export", FAKE_EXPORT)
    fake_adapter.CALLS.clear()
    runner_id = "runner-diffusion"
    with Session(bind=engine) as db:
        DiffusionChannelRepository(db).upsert_settings("fake_export", enabled=True)
        db.commit()
    with Session(bind=engine) as db:
        run = WorkerRunRepository(db).create_queued(
            "diffusion",
            trigger=WorkerRunTrigger.API,
            requested_by=None,
            engine_name=None,
            preset=None,
            config={},
            channel_code="fake_export",
            request={"options": {}},
        )
        db.commit()
        run_id = run.run_id
    try:
        RunnerService(
            _config(runner_id, capabilities=("diffusion",)),
            session_factory=lambda: Session(bind=engine),
        ).run()

        with Session(bind=engine) as db:
            stored = WorkerRunRepository(db).get(run_id)

        assert [call["code"] for call in fake_adapter.CALLS] == ["fake_export"]
        assert fake_adapter.CALLS[0]["run_control"] is not None
        assert stored is not None
        assert stored.status == WorkerRunStatus.SUCCESS
        assert stored.channel_code == "fake_export"
        assert stored.origin_code is None
    finally:
        _cleanup(engine, run_id=run_id, runner_id=runner_id)
        with Session(bind=engine) as db:
            db.execute(delete(DiffusionChannel).where(DiffusionChannel.code == "fake_export"))
            db.commit()
