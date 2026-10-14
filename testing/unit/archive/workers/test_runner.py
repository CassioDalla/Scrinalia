from contextlib import contextmanager

import pytest

from scrinalia.core.logger import logger
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError
from scrinalia.domains.archive.workers import runner


@contextmanager
def _fake_db_factory(sentinel):
    yield sentinel


def test_run_worker_rejects_unknown_worker() -> None:
    with pytest.raises(ValueError, match="Unknown worker"):
        runner.run_worker("nao-existe")


def test_run_worker_forwards_supported_options(monkeypatch) -> None:
    captured: dict = {}
    sentinel = object()

    def fake_worker(db, engine_name=None, preset=None, db_batch_size=None):
        captured.update(db=db, engine_name=engine_name, preset=preset, db_batch_size=db_batch_size)

    monkeypatch.setitem(runner.WORKERS, "fake", fake_worker)

    runner.run_worker(
        "fake",
        engine_name="spacy_ner",
        preset="gpu",
        db_batch_size=16,
        extra={"unknown": "ignored"},
        db_factory=lambda: _fake_db_factory(sentinel),
    )

    assert captured["db"] is sentinel
    assert captured["engine_name"] == "spacy_ner"
    assert captured["preset"] == "gpu"
    assert captured["db_batch_size"] == 16
    assert "unknown" not in captured


def test_run_worker_handles_db_session_and_var_kwargs(monkeypatch) -> None:
    captured: dict = {}
    sentinel = object()

    def fake_worker(db_session, similarity_threshold=0.9, **engine_kwargs):
        captured["db_session"] = db_session
        captured["threshold"] = similarity_threshold
        captured["engine_kwargs"] = engine_kwargs

    monkeypatch.setitem(runner.WORKERS, "fake_session", fake_worker)

    runner.run_worker(
        "fake_session",
        engine_name="ollama_judge",
        extra={"similarity_threshold": 0.8},
        db_factory=lambda: _fake_db_factory(sentinel),
    )

    assert captured["db_session"] is sentinel
    assert captured["threshold"] == 0.8
    assert captured["engine_kwargs"] == {"engine_name": "ollama_judge"}


def test_main_parses_arguments(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(runner, "run_worker", lambda name, **kwargs: captured.update(name=name, **kwargs))

    exit_code = runner.main(
        [
            "ner",
            "--engine",
            "spacy_ner",
            "--preset",
            "gpu",
            "--batch",
            "8",
            "--limit",
            "2",
            "--option",
            "columns_to_extract=a",
        ]
    )

    assert exit_code == 0
    assert captured["name"] == "ner"
    assert captured["engine_name"] == "spacy_ner"
    assert captured["preset"] == "gpu"
    assert captured["db_batch_size"] == 8
    assert captured["limit"] == 2
    assert captured["extra"] == {"columns_to_extract": "a"}


def test_worker_pipeline_order_is_complete() -> None:
    """Every registered worker appears in the pipeline, with the text-dependent ones last."""
    assert "macro-category" in runner.WORKERS
    assert "quality-validator" in runner.WORKERS
    assert "embedding" in runner.WORKERS
    assert runner.PIPELINE_ORDER[-1] == "embedding"
    # The validator reads the tags, the typology and the entities, and the embedding is
    # always last because every text mutation has to happen before it.
    assert runner.PIPELINE_ORDER[-2] == "quality-validator"
    assert runner.PIPELINE_ORDER[-3] == "macro-category"
    assert set(runner.PIPELINE_ORDER) == set(runner.WORKERS)


def test_run_worker_coerces_boolean_options(monkeypatch) -> None:
    """``--option force=false`` must arrive as ``False``, not as the truthy string."""
    captured: dict = {}
    sentinel = object()

    def fake_worker(db, force=None, similarity_threshold=None):
        captured.update(force=force, similarity_threshold=similarity_threshold)

    monkeypatch.setitem(runner.WORKERS, "fake_bool", fake_worker)

    runner.run_worker(
        "fake_bool",
        extra={"force": "false", "similarity_threshold": 0.8},
        db_factory=lambda: _fake_db_factory(sentinel),
    )

    assert captured["force"] is False
    # A non-string value from a programmatic caller is forwarded untouched.
    assert captured["similarity_threshold"] == 0.8


def test_run_worker_forwards_limit_when_the_worker_declares_it(monkeypatch) -> None:
    captured: dict = {}
    sentinel = object()

    def fake_worker(db, limit=None):
        captured["limit"] = limit

    monkeypatch.setitem(runner.WORKERS, "fake_limit", fake_worker)

    runner.run_worker("fake_limit", limit=2, db_factory=lambda: _fake_db_factory(sentinel))

    assert captured["limit"] == 2


def test_run_worker_refuses_limit_for_a_worker_that_does_not_declare_it(monkeypatch) -> None:
    """A cap that silently does nothing is the trap ``--batch`` was; this one is refused.

    ``**engine_kwargs`` does not count as declaring it: a ``limit`` that fell into the engine's
    constructor would be handed to the model and ignored, which is the silent drop again.
    """

    def fake_worker(db, **engine_kwargs):
        raise AssertionError("the worker must not run")

    monkeypatch.setitem(runner.WORKERS, "fake_no_limit", fake_worker)

    with pytest.raises(InvalidWorkerSettingsError, match="não aceita --limit"):
        runner.run_worker("fake_no_limit", limit=2, db_factory=lambda: _fake_db_factory(object()))


def test_a_dropped_flag_is_logged_instead_of_ignored(monkeypatch) -> None:
    """The defect behind the issue: ``--batch`` was accepted and silently discarded."""
    received: list[str] = []
    sink = logger.add(lambda message: received.append(message.record["message"]), level="WARNING")

    def fake_worker(db):
        pass

    monkeypatch.setitem(runner.WORKERS, "fake_no_batch", fake_worker)
    try:
        runner.run_worker("fake_no_batch", db_batch_size=2, db_factory=lambda: _fake_db_factory(object()))
    finally:
        logger.remove(sink)

    assert any("db_batch_size" in message for message in received)
