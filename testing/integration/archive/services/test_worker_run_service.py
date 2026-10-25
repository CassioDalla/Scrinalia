"""Triggering runs, the ledger and the configuration precedence the runner applies."""

from contextlib import contextmanager

import pytest

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import (
    InvalidWorkerSettingsError,
    WorkerRunAlreadyActiveError,
    WorkerRunNotCancellableError,
    WorkerRunNotFoundError,
)
from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.models.operations import WorkerRun
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from scrinalia.domains.archive.schemas.responses import RouteMessageCode
from scrinalia.domains.archive.schemas.system_schema import WorkerRunRequest
from scrinalia.domains.archive.services.worker_run_service import WorkerRunService
from scrinalia.domains.archive.workers import runner
from scrinalia.domains.archive.workers.cancellation import RunControl, checkpoint
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger


@contextmanager
def _shared_session(db):
    """Hands the test's session to the ledger without closing it on the way out."""
    yield db


@pytest.fixture
def ledger(db_session) -> WorkerRunLedger:
    return WorkerRunLedger(session_factory=lambda: _shared_session(db_session))


@pytest.fixture
def service(db_session, ledger) -> WorkerRunService:
    return WorkerRunService(db_session, ledger=ledger)


def test_trigger_queues_the_run_with_its_resolved_config(service, db_session) -> None:
    run = service.trigger("ner", WorkerRunRequest(), requested_by=Author(name="teste"))

    assert run.status == WorkerRunStatus.QUEUED
    assert run.trigger == WorkerRunTrigger.API
    assert run.requested_by == "teste"
    assert run.engine_name == "spacy_ner"
    assert run.preset == "gpu"
    assert run.config["model"] == "pt_core_news_lg"

    # The API only enqueues: the row is the work item, and its request is what a runner reproduces.
    stored = db_session.get(WorkerRun, run.run_id)
    assert stored is not None
    assert stored.status == WorkerRunStatus.QUEUED
    assert stored.request == {
        "engine_name": None,
        "preset": None,
        "db_batch_size": None,
        "options": {},
        "engine_options": {},
    }


def test_trigger_honours_the_persisted_override(service, db_session) -> None:
    WorkerSettingsRepository(db_session).upsert(
        "ner",
        engine_name=None,
        preset="lemmatizer",
        db_batch_size=8,
        options={},
        changed_by=Author(name="teste"),
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
        "ner", engine_name=None, preset="lemmatizer", db_batch_size=8, options={}, changed_by=Author(name="teste")
    )
    db_session.flush()

    runner.run_worker("ner", db_factory=lambda: _shared_session(db_session), ledger=ledger)
    assert captured[-1] == {"engine_name": "spacy_ner", "preset": "lemmatizer", "db_batch_size": 8}

    runner.run_worker(
        "ner", preset="gpu", db_batch_size=32, db_factory=lambda: _shared_session(db_session), ledger=ledger
    )
    assert captured[-1] == {"engine_name": "spacy_ner", "preset": "gpu", "db_batch_size": 32}


# --- the options of a run (#120) ---------------------------------------------------------------


def test_the_runner_writes_the_columns_the_run_read(db_session, ledger, monkeypatch) -> None:
    """
    "Which columns did run #N read?" is a value in the row, not the fingerprint the stamp hashed.

    Nobody named the columns here, so the row carries the worker's own resolution of the code
    default — the only place that can answer the question for the common case.
    """
    seen: dict[str, object] = {}

    def fake_ner(db, **kwargs) -> None:
        seen.update(kwargs)

    monkeypatch.setitem(runner.WORKERS, "ner", fake_ner)

    runner.run_worker("ner", db_factory=lambda: _shared_session(db_session), ledger=ledger)

    stored = WorkerRunRepository(db_session).last_by_worker()["ner"]
    assert stored.status == WorkerRunStatus.SUCCESS
    assert stored.options["columns_to_extract"] == [
        "original_title",
        "admin_bio_history",
        "provenance",
        "scope_content",
    ]
    assert stored.options["force"] is False
    # The row records the resolution; it does not change what the worker was called with.
    assert "columns_to_extract" not in seen


def test_the_engine_pass_through_reaches_the_config_and_the_request(service, db_session) -> None:
    run = service.trigger("ner", WorkerRunRequest(engine_options={"device": "cpu"}))

    assert run.config["device"] == "cpu"
    stored = db_session.get(WorkerRun, run.run_id)
    assert stored is not None
    assert stored.request["engine_options"] == {"device": "cpu"}


def test_a_declared_option_is_refused_as_a_pass_through(service) -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="use 'options'"):
        service.trigger("ner", WorkerRunRequest(engine_options={"force": True}))


def test_the_run_refuses_an_unknown_option_and_a_mistyped_column(service) -> None:
    with pytest.raises(InvalidWorkerSettingsError, match="colunas_to_classify"):
        service.trigger("ner", WorkerRunRequest(options={"colunas_to_classify": ["original_title"]}))

    with pytest.raises(InvalidWorkerSettingsError, match="admin_bio_historia"):
        service.trigger("typology", WorkerRunRequest(options={"columns_to_classify": ["admin_bio_historia"]}))


def test_a_run_cap_is_accepted_for_one_execution(service) -> None:
    """``limit`` is a run option; only the persisted default refuses it."""
    run = service.trigger("ner", WorkerRunRequest(options={"limit": 5}))

    assert run.status == WorkerRunStatus.QUEUED


def test_the_cli_opens_its_run_with_a_lease(db_session, ledger, monkeypatch) -> None:
    """The CLI is a one-shot runner: its row carries the identity and the lease (ADR 0014)."""

    def fake_cleaning(db, **kwargs) -> None:
        pass

    monkeypatch.setitem(runner.WORKERS, "cleaning", fake_cleaning)

    runner.run_worker(
        "cleaning",
        db_factory=lambda: _shared_session(db_session),
        ledger=ledger,
        runner_id="cli:host:1",
        lease_seconds=60,
    )

    stored = WorkerRunRepository(db_session).last_by_worker()["cleaning"]
    assert stored.status == WorkerRunStatus.SUCCESS
    assert stored.runner_id == "cli:host:1"
    assert stored.heartbeat_at is not None
    assert stored.lease_expires_at is not None


# --- Cancelling a run (#72) -------------------------------------------------------------------


def _trigger_and_claim(service: WorkerRunService, db_session) -> int:
    """A run the panel queued, claimed by a runner: the shape a cooperative cancellation needs."""
    run = service.trigger("ner", WorkerRunRequest())
    claimed = WorkerRunRepository(db_session).claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
    assert claimed is not None
    assert claimed.run_id == run.run_id
    return run.run_id


def test_cancelling_an_unclaimed_run_closes_it_and_frees_the_slot(service, db_session) -> None:
    """
    A ``QUEUED`` row no runner claimed never started: nothing is writing, so it closes at once.

    ``duration_ms`` stays NULL because ``started_at`` does: the run did not last zero milliseconds,
    it did not run, and inventing a duration would hide that.
    """
    run = service.trigger("ner", WorkerRunRequest(), requested_by=Author(name="teste"))

    answer = service.cancel(run.run_id, requested_by=Author(name="ana"))

    assert answer.code == RouteMessageCode.WORKER_RUN_CANCELLED
    assert answer.data.status == WorkerRunStatus.CANCELLED
    assert answer.data.cancel_requested_at is not None
    assert answer.data.cancel_requested_by == "ana"
    assert answer.data.finished_at is not None
    assert answer.data.duration_ms is None

    assert WorkerRunRepository(db_session).has_active_run("ner") is False
    assert service.trigger("ner", WorkerRunRequest()).status == WorkerRunStatus.QUEUED


def test_the_request_on_a_claimed_run_keeps_the_slot_and_is_idempotent(service, db_session) -> None:
    """
    The request does not free ``uq_worker_run_active``: the worker is still writing (ADR 0014).

    The second request is the same outcome, not an error, and the first author and instant survive:
    a ledger that let a second click overwrite the decision's author would answer "who stopped it?"
    with the wrong name.
    """
    run_id = _trigger_and_claim(service, db_session)

    first = service.cancel(run_id, requested_by=Author(name="ana"))

    assert first.code == RouteMessageCode.WORKER_RUN_CANCEL_REQUESTED
    assert first.data.status == WorkerRunStatus.RUNNING
    assert first.data.cancel_requested_at is not None
    assert first.data.cancel_requested_by == "ana"
    assert WorkerRunRepository(db_session).has_active_run("ner") is True

    second = service.cancel(run_id, requested_by=Author(name="bia"))

    assert second.code == RouteMessageCode.WORKER_RUN_CANCEL_REQUESTED
    assert second.data.status == WorkerRunStatus.RUNNING
    assert second.data.cancel_requested_by == "ana"


def test_a_run_that_already_finished_answers_conflict(service, db_session) -> None:
    run_id = _trigger_and_claim(service, db_session)
    assert WorkerRunRepository(db_session).finish(run_id, status=WorkerRunStatus.SUCCESS, runner_id="runner-a")

    with pytest.raises(WorkerRunNotCancellableError, match="já terminou"):
        service.cancel(run_id)


def test_cancelling_a_missing_run_answers_not_found(service) -> None:
    with pytest.raises(WorkerRunNotFoundError):
        service.cancel(999_999)


def test_the_runner_closes_cancelled_at_the_batch_boundary(db_session, ledger, monkeypatch) -> None:
    """
    The worker's own checkpoint ends the run as ``CANCELLED``, with no error text.

    No error on purpose: ``archive_error_fingerprint`` is generated from ``error`` and the failures
    screen groups every non-null fingerprint, so a sentence here would present a deliberate stop as
    a root cause.
    """

    def fake_ner(db, run_control=None, **kwargs) -> None:
        assert run_control is not None
        run_control.request_stop()
        checkpoint(run_control)
        raise AssertionError("the checkpoint should have raised")

    monkeypatch.setitem(runner.WORKERS, "ner", fake_ner)

    runner.run_worker(
        "ner",
        db_factory=lambda: _shared_session(db_session),
        ledger=ledger,
        run_control=RunControl(),
    )

    stored = WorkerRunRepository(db_session).last_by_worker()["ner"]
    assert stored.status == WorkerRunStatus.CANCELLED
    assert stored.error is None
    assert stored.error_fingerprint is None
    assert stored.finished_at is not None


def test_a_run_cancelled_before_it_starts_never_builds_the_engine(db_session, ledger, monkeypatch) -> None:
    """The pre-dispatch check is what keeps a cancelled queued run from loading spaCy or torch."""
    called: list[bool] = []

    def fake_ner(db, **kwargs) -> None:
        called.append(True)

    monkeypatch.setitem(runner.WORKERS, "ner", fake_ner)
    control = RunControl()
    control.request_stop()

    runner.run_worker(
        "ner",
        db_factory=lambda: _shared_session(db_session),
        ledger=ledger,
        run_control=control,
    )

    assert called == []
    assert WorkerRunRepository(db_session).last_by_worker()["ner"].status == WorkerRunStatus.CANCELLED


def test_the_worker_reads_the_panel_request_from_the_ledger(db_session, ledger, monkeypatch) -> None:
    """The in-process flag is not the only source: the row carries the panel's request too."""
    run_id = _trigger_and_claim(WorkerRunService(db_session, ledger=ledger), db_session)
    repo = WorkerRunRepository(db_session)

    def fake_ner(db, run_control=None, **kwargs) -> None:
        assert run_control is not None
        repo.request_cancel(run_id, requested_by=Author(name="ana"))
        db.flush()
        checkpoint(run_control)
        raise AssertionError("the checkpoint should have raised")

    monkeypatch.setitem(runner.WORKERS, "ner", fake_ner)

    runner.run_worker(
        "ner",
        db_factory=lambda: _shared_session(db_session),
        ledger=ledger,
        run_id=run_id,
        runner_id="runner-a",
        lease_seconds=60,
    )

    stored = repo.get(run_id, populate_existing=True)
    assert stored is not None
    assert stored.status == WorkerRunStatus.CANCELLED
    assert stored.error is None
