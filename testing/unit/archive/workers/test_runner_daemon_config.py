"""The runner's command line: capabilities, timings and the schema check (ADR 0014)."""

from typing import cast

import pytest

from scrinalia.core.database import SessionFactory
from scrinalia.domains.archive.workers import runner_daemon
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE

#: The schema check must not open a connection in these tests; the functions it calls are faked.
_NO_SESSION = cast(SessionFactory, lambda: None)


def _config(*args: str) -> runner_daemon.RunnerConfig:
    return runner_daemon._build_config(runner_daemon._parse_args(list(args)))


def test_the_default_capabilities_are_the_whole_catalogue() -> None:
    config = _config()

    assert config.capabilities == tuple(WORKER_CATALOGUE)
    assert config.concurrency == 1
    assert config.heartbeat_seconds < config.lease_seconds
    assert config.runner_id.startswith(f"{config.name}:")


def test_a_subset_of_workers_is_accepted_and_trimmed() -> None:
    assert _config("--workers", "ner, embedding").capabilities == ("ner", "embedding")


def test_an_unknown_worker_is_refused() -> None:
    with pytest.raises(SystemExit, match="Unknown worker"):
        _config("--workers", "ner, nao-existe")


def test_a_heartbeat_not_smaller_than_the_lease_is_refused() -> None:
    with pytest.raises(SystemExit, match="smaller"):
        _config("--heartbeat-seconds", "60", "--lease-seconds", "60")


def test_a_stable_runner_id_can_be_given() -> None:
    assert _config("--id", "gpu-01").runner_id == "gpu-01"


def test_the_schema_check_accepts_the_head(monkeypatch) -> None:
    monkeypatch.setattr(runner_daemon, "schema_head", lambda: "abc")
    monkeypatch.setattr(runner_daemon, "current_schema_revision", lambda _: "abc")

    runner_daemon.assert_schema_at_head(_NO_SESSION)


def test_the_schema_check_refuses_a_database_behind_the_code(monkeypatch) -> None:
    monkeypatch.setattr(runner_daemon, "schema_head", lambda: "abc")
    monkeypatch.setattr(runner_daemon, "current_schema_revision", lambda _: "old")

    with pytest.raises(SystemExit, match="migrations"):
        runner_daemon.assert_schema_at_head(_NO_SESSION)


def test_the_schema_check_is_skipped_when_the_head_is_unreadable(monkeypatch) -> None:
    monkeypatch.setattr(runner_daemon, "schema_head", lambda: None)
    monkeypatch.setattr(runner_daemon, "current_schema_revision", lambda _: "unreachable")

    runner_daemon.assert_schema_at_head(_NO_SESSION)
