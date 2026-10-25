"""The runner registry: one row per runner, the heartbeat and the graceful stop (ADR 0014)."""

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
