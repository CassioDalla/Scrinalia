"""The producer identity: what a stamp names besides the fact that the worker ran.

Issues #41 and #70 are the same defect — a stamp that records "ran" while the model, the preset,
the threshold or a dependency changed underneath it. Every test here is about one of those moving
parts moving the identity, or about a queue control deliberately *not* moving it: a forced run must
write the identity of the model, or the next plain run would re-queue the collection again.
"""

from importlib.metadata import PackageNotFoundError

import pytest
from sqlalchemy.dialects import postgresql

from scrinalia.domains.archive import worker_stamp
from scrinalia.domains.archive.models import ArchiveDocument
from scrinalia.domains.archive.worker_stamp import (
    AXIS_RUNTIME_DISTRIBUTIONS,
    FAILURE_STAMP_VALUES,
    NER,
    STAMP_NEUTRAL_OPTIONS,
    identity_stamp_conditions,
    producer_fingerprint,
    runtime_versions,
)
from scrinalia.domains.archive.workers import catalogue


def _fingerprint(**overrides) -> str:
    payload = {
        "axis": "classification",
        "engine_name": "deberta_typology",
        "preset": "cpu_local",
        "engine_config": {"model": "mDeBERTa", "device": "cpu"},
        "worker_options": {"confidence_threshold": 0.4},
    }
    payload.update(overrides)
    return producer_fingerprint(**payload)  # type: ignore[arg-type]


def _sql(conditions) -> str:
    """The predicate as SQL with its literals inlined, so the identity is readable."""
    dialect = postgresql.dialect()
    return " AND ".join(
        str(condition.compile(dialect=dialect, compile_kwargs={"literal_binds": True})) for condition in conditions
    )


def test_the_identity_is_stable_across_calls() -> None:
    """Two calls with the same facts are the same identity, or nothing could ever be settled."""
    assert _fingerprint() == _fingerprint()


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param({"axis": "NER"}, id="axis"),
        pytest.param({"engine_name": "ollama_typology"}, id="engine"),
        pytest.param({"preset": "gpu_cloud"}, id="preset"),
        pytest.param({"engine_config": {"model": "outro", "device": "cpu"}}, id="model"),
        pytest.param({"engine_config": {"model": "mDeBERTa", "device": "cuda"}}, id="device"),
        pytest.param({"worker_options": {"confidence_threshold": 0.6}}, id="declared-option"),
    ],
)
def test_every_part_of_the_producer_moves_the_identity(changed) -> None:
    assert _fingerprint(**changed) != _fingerprint()


@pytest.mark.parametrize("option", sorted(STAMP_NEUTRAL_OPTIONS))
def test_a_queue_control_does_not_move_the_identity(option: str) -> None:
    """A forced or capped run writes the identity of the model, not of the force."""
    assert _fingerprint(worker_options={"confidence_threshold": 0.4, option: "x"}) == _fingerprint()


def test_the_key_order_of_the_config_does_not_move_the_identity() -> None:
    """``describe_config`` merges dictionaries; their order is not a fact about the producer."""
    assert _fingerprint(engine_config={"device": "cpu", "model": "mDeBERTa"}) == _fingerprint()


def test_every_axis_declares_the_libraries_that_can_invalidate_it() -> None:
    """A new axis must say which runtime can invalidate its answers, or the gate is a silent zero."""
    assert set(AXIS_RUNTIME_DISTRIBUTIONS) == set(catalogue.ENGINE_AXES)


def test_a_dependency_bump_moves_the_identity(monkeypatch) -> None:
    """
    The failure #41 measured: ``torch`` moved, the preset did not, and every vector went stale.

    A hash of the preset alone could not have caught it, which is why the installed versions are
    read from the distribution metadata — no import, no engine, just the version.
    """
    monkeypatch.setattr(worker_stamp, "distribution_version", lambda package: "1.0.0")
    before = _fingerprint()

    monkeypatch.setattr(worker_stamp, "distribution_version", lambda package: "2.0.0")

    assert _fingerprint() != before


def test_a_missing_distribution_is_reported_and_not_raised(monkeypatch) -> None:
    """The panel counts a queue; a 500 because a heavy dependency is absent would hide it."""

    def missing(package: str) -> str:
        raise PackageNotFoundError(package)

    monkeypatch.setattr(worker_stamp, "distribution_version", missing)

    assert runtime_versions("embeddings") == {"torch": "absent", "sentence-transformers": "absent"}
    assert len(_fingerprint()) == 64


def test_an_unknown_axis_has_no_runtime() -> None:
    assert runtime_versions(None) == {}
    assert runtime_versions("inexistente") == {}


def test_the_predicate_asks_for_the_identity_or_a_failure_mark() -> None:
    """Pending is "no stamp, another producer, or a failure" — never "any value but the identity"."""
    conditions = identity_stamp_conditions(ArchiveDocument.execution_log, NER, "identidade")

    assert len(conditions) == 1
    sql = _sql(conditions)
    assert "worker_ner_v2" in sql
    assert "identidade" in sql
    for failure in FAILURE_STAMP_VALUES:
        assert failure in sql


def test_force_drops_the_stamp_clause() -> None:
    """``force`` widens the queue; the worker's cursor is what keeps that run finite."""
    assert identity_stamp_conditions(ArchiveDocument.execution_log, NER, "identidade", force=True) == []
