"""The failures screen reads two ledgers as one question.

What the archivist needs is *what is breaking, how often, and since when* — not which table happened
to record it. These tests pin the grouping across both ledgers, the window that keeps the screen
about the present, and the worker filter that must not silently keep API failures around.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from scrinalia.domains.archive.models.enums import FailureSource, WorkerRunStatus, WorkerRunTrigger
from scrinalia.domains.archive.models.operations import ApiError, WorkerRun
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.services.failure_service import FailureService


def failed_run(
    db, *, worker: str = "ner", kind: str = "RuntimeError", message: str = "boom", at: datetime | None = None
):
    """One failed execution, optionally backdated so the window can be exercised."""
    repo = WorkerRunRepository(db)
    run = repo.create_running(
        worker,
        trigger=WorkerRunTrigger.CLI,
        requested_by=None,
        engine_name=None,
        preset=None,
        config={},
    )
    repo.finish(run.run_id, status=WorkerRunStatus.FAILED, error=message, error_kind=kind)

    if at is not None:
        db.execute(
            update(WorkerRun).where(WorkerRun.id == run.run_id).values(queued_at=at, started_at=at, finished_at=at)
        )
        db.flush()

    return run.run_id


def api_failure(
    db,
    *,
    kind: str = "RuntimeError",
    message: str = "boom",
    path: str = "/api/v1/documents",
    at: datetime | None = None,
):
    row = ApiError(
        request_id="trace-42",
        method="GET",
        path=path,
        status_code=500,
        message=f"{kind}: {message}",
    )
    if at is not None:
        row.occurred_at = at
    db.add(row)
    db.flush()
    return row.id


def test_the_same_cause_in_two_executions_is_one_group(db_session) -> None:
    failed_run(db_session, message="modelo ausente")
    failed_run(db_session, message="modelo ausente")

    response = FailureService(db_session).list_groups()

    assert response.total == 1
    group = response.items[0]
    assert group.occurrences == 2
    assert group.sources == [FailureSource.WORKER]
    assert group.worker_names == ["ner"]
    assert group.sample == "RuntimeError: modelo ausente"


def test_a_cause_that_broke_a_worker_and_a_request_is_one_group(db_session) -> None:
    """The fingerprint is the same function over both messages; splitting it would hide the cause."""
    failed_run(db_session, message="boom")
    api_failure(db_session, message="boom")

    response = FailureService(db_session).list_groups()

    assert response.total == 1
    group = response.items[0]
    assert group.occurrences == 2
    assert sorted(group.sources) == [FailureSource.API, FailureSource.WORKER]
    assert group.last_path == "/api/v1/documents"
    assert group.last_request_id == "trace-42"


def test_the_classes_do_not_collapse_into_one_another(db_session) -> None:
    failed_run(db_session, kind="TimeoutError", message="boom")
    failed_run(db_session, kind="ValueError", message="boom")

    response = FailureService(db_session).list_groups()

    assert response.total == 2


def test_the_window_leaves_out_what_is_old(db_session) -> None:
    old = datetime.now(UTC) - timedelta(days=40)
    failed_run(db_session, message="erro antigo", at=old)
    failed_run(db_session, message="erro de agora")

    response = FailureService(db_session).list_groups(days=30)

    assert response.total == 1
    assert "agora" in response.items[0].sample


def test_the_worker_filter_drops_the_api_only_groups(db_session) -> None:
    """A group with no worker to match is not "this worker failed" — leaving it in would be a lie."""
    failed_run(db_session, worker="ner", message="erro do ner")
    failed_run(db_session, worker="typology", message="erro da tipologia")
    api_failure(db_session, message="erro da api")

    response = FailureService(db_session).list_groups(worker="ner")

    assert response.total == 1
    assert response.items[0].worker_names == ["ner"]


def test_the_groups_come_newest_first(db_session) -> None:
    now = datetime.now(UTC)
    failed_run(db_session, message="mais antigo", at=now - timedelta(days=2))
    failed_run(db_session, message="mais novo", at=now - timedelta(hours=1))

    response = FailureService(db_session).list_groups()

    assert [group.sample for group in response.items] == ["RuntimeError: mais novo", "RuntimeError: mais antigo"]
