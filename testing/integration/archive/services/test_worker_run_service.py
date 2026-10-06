"""Triggering runs, the ledger and the configuration precedence the runner applies."""

from contextlib import contextmanager

import pytest

from memoria_curitibana.domains.archive.exceptions import WorkerRunAlreadyActiveError
from memoria_curitibana.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from memoria_curitibana.domains.archive.repository.worker_run_repo import WorkerRunRepository
from memoria_curitibana.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from memoria_curitibana.domains.archive.schemas.system_schema import WorkerRunRequest
from memoria_curitibana.domains.archive.services.worker_run_service import WorkerRunService
from memoria_curitibana.domains.archive.workers import runner
from memoria_curitibana.domains.archive.workers.ledger import WorkerRunLedger


@contextmanager
def _shared_session(db):
    """Hands the test's session to the ledger without closing it on the way out."""
    yield db


class FakeRuntime:
    """Records what was submitted; the real pool is not exercised here."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, object]] = []

    def submit(self, worker_name, run_id, resolved) -> None:
        self.calls.append((worker_name, run_id, resolved))


@pytest.fixture
def ledger(db_session) -> WorkerRunLedger:
    return WorkerRunLedger(session_factory=lambda: _shared_session(db_session))


@pytest.fixture
def runtime() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def service(db_session, runtime, ledger) -> WorkerRunService:
    return WorkerRunService(db_session, runtime, ledger=ledger)


def test_trigger_queues_the_run_with_its_resolved_config(service, runtime, db_session) -> None:
    run = service.trigger("ner", WorkerRunRequest(requested_by="teste"))

    assert run.status == WorkerRunStatus.QUEUED
    assert run.trigger == WorkerRunTrigger.API
    assert run.requested_by == "teste"
    assert run.engine_name == "spacy_ner"
    assert run.preset == "gpu"
    assert run.config["model"] == "pt_core_news_lg"

    assert len(runtime.calls) == 1
    worker_name, run_id, _resolved = runtime.calls[0]
    assert (worker_name, run_id) == ("ner", run.run_id)
    # The row is already committed when the executor is handed the id.
    assert WorkerRunRepository(db_session).get(run.run_id).status == WorkerRunStatus.QUEUED


def test_trigger_honours_the_persisted_override(service, db_session) -> None:
    WorkerSettingsRepository(db_session).upsert(
        "ner",
        engine_name=None,
        preset="lemmatizer",
        db_batch_size=8,
        options={},
        changed_by="teste",
    )
    db_session.flush()

    run = service.trigger("ner", WorkerRunRequest())

    assert run.preset == "lemmatizer"
    assert run.config["disable"] == ["ner", "parser"]


def test_a_second_run_for_the_same_worker_is_refused_by_the_database(service, db_session) -> None:
    WorkerRunRepository(db_session).create_queued(
        "ner",
        trigger=WorkerRunTrigger.API,
        requested_by=None,
        engine_name="spacy_ner",
        preset="gpu",
        config={},
    )
    db_session.flush()

    with pytest.raises(WorkerRunAlreadyActiveError):
        service.trigger("ner", WorkerRunRequest())


def test_the_cli_ledger_refuses_to_open_a_second_run(db_session, ledger) -> None:
    first = ledger.start(
        "ner", trigger=WorkerRunTrigger.CLI, requested_by=None, engine_name=None, preset=None, config={}
    )
    assert first is not None

    with pytest.raises(WorkerRunAlreadyActiveError):
        ledger.start("ner", trigger=WorkerRunTrigger.CLI, requested_by=None, engine_name=None, preset=None, config={})


def test_recover_orphans_closes_the_runs_a_dead_process_left(db_session) -> None:
    repository = WorkerRunRepository(db_session)
    queued = repository.create_queued(
        "ner", trigger=WorkerRunTrigger.API, requested_by=None, engine_name=None, preset=None, config={}
    )
    running = repository.create_running(
        "typology", trigger=WorkerRunTrigger.CLI, requested_by=None, engine_name=None, preset=None, config={}
    )
    db_session.flush()

    assert repository.recover_orphans() == 2

    assert repository.get(queued.run_id).status == WorkerRunStatus.INTERRUPTED
    assert repository.get(running.run_id).status == WorkerRunStatus.INTERRUPTED
    assert "processo anterior" in (repository.get(running.run_id).error or "")


def test_the_runner_records_a_successful_run(db_session, ledger, monkeypatch) -> None:
    def fake_cleaning(db, **kwargs) -> None:
        assert db is db_session

    monkeypatch.setitem(runner.WORKERS, "cleaning", fake_cleaning)

    runner.run_worker("cleaning", db_factory=lambda: _shared_session(db_session), ledger=ledger)

    stored = WorkerRunRepository(db_session).last_by_worker()["cleaning"]
    assert stored.status == WorkerRunStatus.SUCCESS
    assert stored.trigger == WorkerRunTrigger.CLI
    assert stored.duration_ms is not None


def test_the_runner_records_a_failure_and_reraises(db_session, ledger, monkeypatch) -> None:
    def broken(db, **kwargs) -> None:
        raise RuntimeError("modelo não carregou")

    monkeypatch.setitem(runner.WORKERS, "cleaning", broken)

    with pytest.raises(RuntimeError, match="modelo não carregou"):
        runner.run_worker("cleaning", db_factory=lambda: _shared_session(db_session), ledger=ledger)

    stored = WorkerRunRepository(db_session).last_by_worker()["cleaning"]
    assert stored.status == WorkerRunStatus.FAILED
    assert "modelo não carregou" in (stored.error or "")


def test_the_runner_precedence_is_explicit_then_override_then_default(db_session, ledger, monkeypatch) -> None:
    captured: list[dict] = []

    def capturing(db, engine_name=None, preset=None, db_batch_size=None, **kwargs) -> None:
        captured.append({"engine_name": engine_name, "preset": preset, "db_batch_size": db_batch_size})

    monkeypatch.setitem(runner.WORKERS, "ner", capturing)
    WorkerSettingsRepository(db_session).upsert(
        "ner", engine_name=None, preset="lemmatizer", db_batch_size=8, options={}, changed_by="teste"
    )
    db_session.flush()

    runner.run_worker("ner", db_factory=lambda: _shared_session(db_session), ledger=ledger)
    assert captured[-1] == {"engine_name": "spacy_ner", "preset": "lemmatizer", "db_batch_size": 8}

    runner.run_worker(
        "ner", preset="gpu", db_batch_size=32, db_factory=lambda: _shared_session(db_session), ledger=ledger
    )
    assert captured[-1] == {"engine_name": "spacy_ner", "preset": "gpu", "db_batch_size": 32}
