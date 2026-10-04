from contextlib import contextmanager

import pytest

from memoria_curitibana.domains.archive.workers import runner


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
        ["ner", "--engine", "spacy_ner", "--preset", "gpu", "--batch", "8", "--option", "columns_to_extract=a"]
    )

    assert exit_code == 0
    assert captured["name"] == "ner"
    assert captured["engine_name"] == "spacy_ner"
    assert captured["preset"] == "gpu"
    assert captured["db_batch_size"] == 8
    assert captured["extra"] == {"columns_to_extract": "a"}


def test_worker_pipeline_order_is_complete() -> None:
    """Every registered worker appears in the pipeline, with the text-dependent ones last."""
    assert "macro-category" in runner.WORKERS
    assert "embedding" in runner.WORKERS
    assert runner.PIPELINE_ORDER[-1] == "embedding"
    assert runner.PIPELINE_ORDER[-2] == "macro-category"
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
