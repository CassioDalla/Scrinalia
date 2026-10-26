"""The queue protocol of the run ledger: claim, lease, start, finish and orphan recovery.

ADR 0014 makes a ``QUEUED`` row the work item an external runner claims. These tests pin the
protocol's invariants against PostgreSQL: one runner gets a row, the row carries the request, the
lease is the only liveness proof, and a runner that lost the lease cannot close or rewrite the row.

The timestamps are PostgreSQL's ``now()``, which is the transaction's start time: within one
``db_session`` the clock does not move, which is exactly what makes the comparisons below stable.
A test that needs the clock to move sets the lease directly; the sweep then reads the same fixed
``now()`` and the relative order is what it asserts.
"""

from sqlalchemy import delete, func, update
from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.models.operations import WorkerRun
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.schemas.system_schema import WorkerRunDTO


def _queued(repo: WorkerRunRepository, worker_name: str = "ner", request: dict | None = None) -> WorkerRunDTO:
    """Accepts one queued run, with the fields the API's trigger fills."""
    return repo.create_queued(
        worker_name,
        trigger=WorkerRunTrigger.API,
        requested_by=None,
        engine_name="spacy_ner",
        preset="gpu",
        config={"model": "pt_core_news_lg"},
        request=request,
    )


def _set_lease(db: Session, run_id: int, *, seconds: int) -> None:
    """Moves one row's lease relative to the transaction's ``now()``; negative means expired."""
    db.execute(
        update(WorkerRun)
        .where(WorkerRun.id == run_id)
        .values(lease_expires_at=func.now() + func.make_interval(0, 0, 0, 0, 0, 0, seconds))
    )
    db.flush()


def test_the_claim_takes_the_oldest_queued_row_and_carries_its_request(db_session) -> None:
    repo = WorkerRunRepository(db_session)
    older = _queued(repo, "ner", {"engine_name": "spacy_ner", "options": {"force": True}})
    newer = _queued(repo, "typology")

    claimed = repo.claim_next(["ner", "typology"], runner_id="runner-a", lease_seconds=60)

    assert claimed is not None
    assert (claimed.run_id, claimed.worker_name) == (older.run_id, "ner")
    assert claimed.request == {"engine_name": "spacy_ner", "options": {"force": True}}

    stored = repo.get(claimed.run_id)
    assert stored is not None
    assert stored.status == WorkerRunStatus.RUNNING
    assert stored.runner_id == "runner-a"
    assert stored.started_at is not None
    assert stored.heartbeat_at is not None
    assert stored.lease_expires_at is not None

    newer_row = repo.get(newer.run_id)
    assert newer_row is not None
    assert newer_row.status == WorkerRunStatus.QUEUED


def test_the_claim_ignores_a_worker_the_runner_does_not_advertise(db_session) -> None:
    repo = WorkerRunRepository(db_session)
    run = _queued(repo, "ner")

    assert repo.claim_next(["typology"], runner_id="runner-a", lease_seconds=60) is None

    stored = repo.get(run.run_id)
    assert stored is not None
    assert stored.status == WorkerRunStatus.QUEUED


def test_the_claim_of_an_empty_queue_returns_nothing(db_session) -> None:
    assert WorkerRunRepository(db_session).claim_next(["ner"], runner_id="runner-a", lease_seconds=60) is None


def test_the_heartbeat_extends_only_the_lease_of_the_runs_it_tracks(db_session) -> None:
    repo = WorkerRunRepository(db_session)
    _queued(repo, "ner")
    _queued(repo, "typology")
    first = repo.claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
    second = repo.claim_next(["typology"], runner_id="runner-b", lease_seconds=60)
    assert first is not None and second is not None

    before = repo.get(first.run_id)
    other_before = repo.get(second.run_id)
    assert before is not None and before.lease_expires_at is not None
    assert other_before is not None and other_before.lease_expires_at is not None

    assert repo.heartbeat("runner-a", lease_seconds=600, run_ids=[first.run_id]) == 1

    db_session.expire_all()
    after = repo.get(first.run_id)
    other_after = repo.get(second.run_id)
    assert after is not None and after.lease_expires_at is not None
    assert other_after is not None
    assert after.lease_expires_at > before.lease_expires_at
    assert other_after.lease_expires_at == other_before.lease_expires_at


def test_the_sweeper_interrupts_only_the_expired_claim(db_session) -> None:
    repo = WorkerRunRepository(db_session)
    _queued(repo, "ner")
    _queued(repo, "typology")
    expired = repo.claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
    live = repo.claim_next(["typology"], runner_id="runner-b", lease_seconds=60)
    assert expired is not None and live is not None

    _set_lease(db_session, expired.run_id, seconds=-1)
    assert repo.expire_stale_leases() == 1

    db_session.expire_all()
    expired_row = repo.get(expired.run_id)
    live_row = repo.get(live.run_id)
    assert expired_row is not None and live_row is not None
    assert expired_row.status == WorkerRunStatus.INTERRUPTED
    assert expired_row.error is not None
    assert "parou de enviar sinal" in expired_row.error
    assert expired_row.finished_at is not None
    assert live_row.status == WorkerRunStatus.RUNNING


def test_the_finish_is_fenced_by_the_runner_that_claimed_the_row(db_session) -> None:
    repo = WorkerRunRepository(db_session)
    _queued(repo, "ner")
    claimed = repo.claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
    assert claimed is not None

    assert repo.finish(claimed.run_id, status=WorkerRunStatus.SUCCESS, runner_id="runner-b") is False
    db_session.expire_all()
    still_running = repo.get(claimed.run_id)
    assert still_running is not None
    assert still_running.status == WorkerRunStatus.RUNNING

    assert repo.finish(claimed.run_id, status=WorkerRunStatus.SUCCESS, runner_id="runner-a") is True
    db_session.expire_all()
    closed = repo.get(claimed.run_id)
    assert closed is not None
    assert closed.status == WorkerRunStatus.SUCCESS
    assert closed.finished_at is not None
    assert closed.duration_ms is not None


def test_record_start_writes_the_effective_configuration_only_for_the_owner(db_session) -> None:
    repo = WorkerRunRepository(db_session)
    _queued(repo, "ner")
    claimed = repo.claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
    assert claimed is not None

    assert (
        repo.record_start(
            claimed.run_id,
            runner_id="runner-b",
            engine_name="x",
            preset="y",
            config={"a": 1},
            options={"b": 2},
        )
        is False
    )
    db_session.expire_all()
    untouched = repo.get(claimed.run_id)
    assert untouched is not None
    assert untouched.engine_name == "spacy_ner"

    assert (
        repo.record_start(
            claimed.run_id,
            runner_id="runner-a",
            engine_name="x",
            preset="y",
            config={"a": 1},
            options={"b": 2},
        )
        is True
    )
    db_session.expire_all()
    recorded = repo.get(claimed.run_id)
    assert recorded is not None
    assert (recorded.engine_name, recorded.preset) == ("x", "y")
    assert recorded.config == {"a": 1}
    assert recorded.options == {"b": 2}


def test_a_finished_run_is_not_renewed_by_a_heartbeat(db_session) -> None:
    repo = WorkerRunRepository(db_session)
    _queued(repo, "ner")
    claimed = repo.claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
    assert claimed is not None
    assert repo.finish(claimed.run_id, status=WorkerRunStatus.SUCCESS, runner_id="runner-a") is True

    assert repo.heartbeat("runner-a", lease_seconds=600) == 0


def test_a_cli_run_can_open_its_own_lease(db_session) -> None:
    """The CLI is a one-shot runner: it gives itself the identity and the lease a daemon would."""
    run = WorkerRunRepository(db_session).create_running(
        "ner",
        trigger=WorkerRunTrigger.CLI,
        requested_by=None,
        engine_name="spacy_ner",
        preset="gpu",
        config={},
        runner_id="cli:host:1",
        lease_seconds=60,
    )

    assert run.runner_id == "cli:host:1"
    assert run.heartbeat_at is not None
    assert run.lease_expires_at is not None


def test_a_claim_committed_by_one_session_is_invisible_to_the_next(engine) -> None:
    """
    The claim is a database write, not a process lock.

    Two sessions on the same database are the shape of two runners: the first commits the row as
    ``RUNNING``, and the second finds no queued row. The concurrent form of the same race is
    ``FOR UPDATE SKIP LOCKED``, which PostgreSQL guarantees; what this test pins is that the claim's
    predicate reads the committed state and that a second claim cannot take the same row.
    """
    run_id: int | None = None
    with Session(bind=engine) as setup:
        run = WorkerRunRepository(setup).create_queued(
            "ner",
            trigger=WorkerRunTrigger.API,
            requested_by=None,
            engine_name="spacy_ner",
            preset="gpu",
            config={},
        )
        setup.commit()
        run_id = run.run_id

    try:
        with Session(bind=engine) as first:
            claimed = WorkerRunRepository(first).claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
            first.commit()
        assert claimed is not None
        assert claimed.run_id == run_id

        with Session(bind=engine) as second:
            assert WorkerRunRepository(second).claim_next(["ner"], runner_id="runner-b", lease_seconds=60) is None
            second.commit()
    finally:
        if run_id is not None:
            with Session(bind=engine) as cleanup:
                cleanup.execute(delete(WorkerRun).where(WorkerRun.id == run_id))
                cleanup.commit()


# --- Cancellation (#72) -----------------------------------------------------------------------


def test_an_unclaimed_queued_run_is_closed_cancelled(db_session) -> None:
    """
    A row no runner claimed never started: the API closes it at once and the slot is free.

    The request timestamp and its author are written by the same statement, and ``duration_ms``
    stays NULL because the run has no ``started_at``.
    """
    repo = WorkerRunRepository(db_session)
    run = _queued(repo)

    assert repo.close_unclaimed(run.run_id, requested_by=Author(name="ana")) is True

    stored = repo.get(run.run_id, populate_existing=True)
    assert stored is not None
    assert stored.status == WorkerRunStatus.CANCELLED
    assert stored.cancel_requested_at is not None
    assert stored.cancel_requested_by == "ana"
    assert stored.finished_at is not None
    assert stored.duration_ms is None
    assert repo.is_cancel_requested(run.run_id) is True
    # A second immediate close is not a second write: the row is already terminal.
    assert repo.close_unclaimed(run.run_id, requested_by=Author(name="bia")) is False


def test_the_request_on_a_claimed_run_keeps_it_running_and_holding_the_slot(db_session) -> None:
    """
    The request is not a status: the row stays ``RUNNING`` until the worker honours it.

    This is the invariant ``uq_worker_run_active`` depends on (ADR 0014 decision 9). The first
    author and instant survive a repeated request, and the close the runner writes is ``CANCELLED``
    with no error text — a cancellation is not a failure the failures screen should group.
    """
    repo = WorkerRunRepository(db_session)
    run = _queued(repo)
    claimed = repo.claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
    assert claimed is not None and claimed.run_id == run.run_id

    assert repo.close_unclaimed(run.run_id, requested_by=Author(name="ana")) is False
    assert repo.request_cancel(run.run_id, requested_by=Author(name="ana")) is True

    requested = repo.get(run.run_id, populate_existing=True)
    assert requested is not None
    assert requested.status == WorkerRunStatus.RUNNING
    assert requested.cancel_requested_at is not None
    assert requested.cancel_requested_by == "ana"
    assert repo.has_active_run("ner") is True

    assert repo.request_cancel(run.run_id, requested_by=Author(name="bia")) is False
    still = repo.get(run.run_id, populate_existing=True)
    assert still is not None
    assert still.cancel_requested_by == "ana"

    assert repo.finish(run.run_id, status=WorkerRunStatus.CANCELLED, runner_id="runner-a") is True

    closed = repo.get(run.run_id, populate_existing=True)
    assert closed is not None
    assert closed.status == WorkerRunStatus.CANCELLED
    assert closed.error is None
    assert closed.error_fingerprint is None
    assert repo.has_active_run("ner") is False


def test_a_cancelled_scheduled_run_is_never_retried(db_session) -> None:
    """ADR 0014 decision 9: a deliberate stop is not a failure the scheduler retries."""
    repo = WorkerRunRepository(db_session)
    failed = _queued(repo)
    cancelled = _queued(repo, "typology")
    # ``_queued`` creates API rows; the retry eligibility is the SCHEDULE trigger's, so mark both.
    db_session.execute(
        update(WorkerRun)
        .where(WorkerRun.id.in_([failed.run_id, cancelled.run_id]))
        .values(trigger=WorkerRunTrigger.SCHEDULE)
    )
    db_session.flush()

    claimed = repo.claim_next(["ner"], runner_id="runner-a", lease_seconds=60)
    assert claimed is not None and claimed.run_id == failed.run_id
    assert repo.finish(failed.run_id, status=WorkerRunStatus.FAILED, runner_id="runner-a") is True
    assert repo.close_unclaimed(cancelled.run_id, requested_by=Author(name="ana")) is True

    retried = repo.due_retries(max_attempts=3)

    assert [run.id for run in retried] == [failed.run_id]
