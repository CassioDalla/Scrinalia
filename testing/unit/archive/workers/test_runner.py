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


def test_run_worker_coerces_options_by_the_declared_type(monkeypatch) -> None:
    """A number has to arrive as a number: ``0.5 > "0.6"`` is a TypeError at the bottom of a run."""
    captured: dict = {}
    sentinel = object()

    def fake_worker(db, confidence_threshold: float = 0.4, repeat_threshold: int = 3, force: bool = False):
        captured.update(confidence_threshold=confidence_threshold, repeat_threshold=repeat_threshold, force=force)

    monkeypatch.setitem(runner.WORKERS, "fake_types", fake_worker)

    runner.run_worker(
        "fake_types",
        extra={"confidence_threshold": "0.6", "repeat_threshold": "5", "force": "true"},
        db_factory=lambda: _fake_db_factory(sentinel),
    )

    assert captured == {"confidence_threshold": 0.6, "repeat_threshold": 5, "force": True}


@pytest.mark.parametrize(
    ("option", "message"),
    [
        ({"confidence_threshold": "muito"}, "espera um número"),
        ({"repeat_threshold": "muitos"}, "espera um inteiro"),
        ({"force": "talvez"}, "booleana"),
        ({"columns_to_extract": "original_title"}, "lista ou um objeto"),
    ],
)
def test_a_value_that_cannot_be_read_is_refused_at_the_top(monkeypatch, option: dict, message: str) -> None:
    """A flag that would fail deep inside a run is refused before the run starts.

    The list case is the one that used to corrupt silently: the worker would take the string and
    iterate it character by character, so ``getattr(ArchiveDocument, "o")`` blew up inside the
    predicate. The type is read from the declared default — an option whose default is ``None``
    carries no type and is forwarded as the string it is.
    """

    def fake_worker(
        db,
        confidence_threshold: float = 0.4,
        repeat_threshold: int = 3,
        force: bool = False,
        columns_to_extract: list[str] = ["original_title"],  # noqa: B006 - the default is the declaration
    ):
        raise AssertionError("the worker must not be reached")

    monkeypatch.setitem(runner.WORKERS, "fake_refused", fake_worker)

    with pytest.raises(InvalidWorkerSettingsError, match=message):
        runner.run_worker("fake_refused", extra=option, db_factory=lambda: _fake_db_factory(object()))


def test_a_cap_must_be_positive() -> None:
    """``--limit 0`` reads nothing and exits successfully, which reads as "the queue is empty"."""
    with pytest.raises(SystemExit):
        runner.main(["embedding", "--limit", "0"])


# --- the engine pass-through (#120) -------------------------------------------------------------


def test_main_parses_the_engine_pass_through_apart_from_the_options(monkeypatch) -> None:
    """
    The two doors are parsed apart: ``--option`` is validated by the worker's signature, and
    ``--engine-option`` is the raw pass-through the constructor validates.
    """
    captured: dict = {}
    monkeypatch.setattr(runner, "run_worker", lambda name, **kwargs: captured.update(name=name, **kwargs))

    exit_code = runner.main(
        [
            "ner",
            "--option",
            "columns_to_extract=original_title",
            "--engine-option",
            "device=cpu",
            "--engine-option",
            "disable=ner,parser",
        ]
    )

    assert exit_code == 0
    assert captured["extra"] == {"columns_to_extract": "original_title"}
    assert captured["engine_options"] == {"device": "cpu", "disable": ["ner", "parser"]}


def test_the_pass_through_is_coerced_by_the_type_the_preset_declares(monkeypatch) -> None:
    """``batch_size=16`` reaches the constructor as a number, not as the string the shell gave."""
    captured: dict = {}
    monkeypatch.setattr(runner, "run_worker", lambda name, **kwargs: captured.update(name=name, **kwargs))

    runner.main(["embedding", "--engine-option", "batch_size=16"])

    assert captured["engine_options"] == {"batch_size": 16}


def test_an_unknown_pass_through_key_keeps_the_string_the_shell_gave(monkeypatch) -> None:
    """The key is the library's: the engine validates the value, and the CLI invents no type for it."""
    captured: dict = {}
    monkeypatch.setattr(runner, "run_worker", lambda name, **kwargs: captured.update(name=name, **kwargs))

    runner.main(["ner", "--engine-option", "max_length=256"])

    assert captured["engine_options"] == {"max_length": "256"}


def test_a_pass_through_without_a_value_is_a_usage_error(monkeypatch) -> None:
    with pytest.raises(SystemExit):
        runner.main(["ner", "--engine-option", "device"])


def test_the_first_signal_asks_and_the_second_forces() -> None:
    """
    ``SIGINT``/``SIGTERM`` give the CLI the same ending as the panel, in two steps (#72).

    The first signal is a request the worker honours at the next batch boundary; the second is the
    operator insisting, and ``run_worker`` closes the row ``CANCELLED`` before the process exits.
    """
    control = runner.RunControl()
    stop = runner._StopOnSignal(control)

    stop(2, None)
    assert control.stop_requested is True

    with pytest.raises(KeyboardInterrupt):
        stop(2, None)
