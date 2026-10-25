"""The runner registry: one row per runner, the heartbeat and the graceful stop (ADR 0014)."""

from sqlalchemy import func, update

from scrinalia.domains.archive.models.operations import WorkerRunner
from scrinalia.domains.archive.repository.worker_runner_repo import WorkerRunnerRepository


def _register(
    repo: WorkerRunnerRepository,
    runner_id: str = "runner-a",
    *,
    name: str = "gpu",
    capabilities: tuple[str, ...] = ("ner", "embedding"),
) -> None:
    repo.register(
        runner_id,
        name=name,
        hostname="gpu-01",
        version="1.6.0",
        capabilities=list(capabilities),
        concurrency=1,
        heartbeat_seconds=15,
    )


def test_a_runner_registers_and_is_listed(db_session) -> None:
    repo = WorkerRunnerRepository(db_session)
    _register(repo)

    rows = repo.list()

    assert len(rows) == 1
    assert rows[0].runner_id == "runner-a"
    assert rows[0].capabilities == ["ner", "embedding"]
    assert rows[0].version == "1.6.0"
    assert rows[0].stopped_at is None


def test_registering_the_same_id_refreshes_the_row(db_session) -> None:
    repo = WorkerRunnerRepository(db_session)
    _register(repo)
    _register(repo, name="gpu-2", capabilities=("ner",))

    db_session.expire_all()
    rows = repo.list()

    assert len(rows) == 1
    assert rows[0].name == "gpu-2"
    assert rows[0].capabilities == ["ner"]


def test_the_heartbeat_and_the_stop_move_the_row(db_session) -> None:
    repo = WorkerRunnerRepository(db_session)
    _register(repo)

    assert repo.heartbeat("runner-a") is True
    assert repo.stop("runner-a") is True

    db_session.expire_all()
    assert repo.list()[0].stopped_at is not None
    assert repo.heartbeat("runner-a") is False
    assert repo.stop("runner-a") is False


def test_the_panel_read_marks_an_old_heartbeat_and_a_stop_offline(db_session) -> None:
    repo = WorkerRunnerRepository(db_session)
    _register(repo)
    assert repo.list_for_panel()[0].online is True

    db_session.execute(
        update(WorkerRunner)
        .where(WorkerRunner.runner_id == "runner-a")
        .values(last_heartbeat_at=func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 100))
    )
    db_session.flush()
    assert repo.list_for_panel()[0].online is False

    # A fresh registration is a heartbeat again; a graceful stop is offline even with a fresh one.
    _register(repo)
    assert repo.list_for_panel()[0].online is True
    repo.stop("runner-a")
    db_session.flush()

    panel = repo.list_for_panel()
    assert panel[0].stopped_at is not None
    assert panel[0].online is False
