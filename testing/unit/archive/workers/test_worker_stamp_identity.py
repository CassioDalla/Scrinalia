"""The producer identity: what a stamp names besides the fact that the worker ran.

Issues #41 and #70 are the same defect — a stamp that records "ran" while the model, the preset,
the threshold or a dependency changed underneath it. Every test here is about one of those moving
parts moving the identity, or about a queue control deliberately *not* moving it: a forced run must
write the identity of the model, or the next plain run would re-queue the collection again.

Issue #137 is the other half of the same slot: the identity-keyed write path refuses a status. The
tests below pin that a ``"DONE"`` — the value 1,691 NER rows really carry — is a ``ValueError`` now,
and that the name for "a run happened and the producer is unknown" is not a fingerprint.
"""

from importlib.metadata import PackageNotFoundError

import pytest
from sqlalchemy.dialects import postgresql

from scrinalia.domains.archive import worker_stamp
from scrinalia.domains.archive.models import ArchiveDocument
from scrinalia.domains.archive.worker_stamp import (
    AXIS_RUNTIME_DISTRIBUTIONS,
    EMBEDDING,
    FAILURE_STAMP_VALUES,
    MACRO_CATEGORY,
    NER,
    PRODUCER_UNKNOWN,
    QUALITY_VALIDATOR,
    STAMP_NEUTRAL_OPTIONS,
    STAMP_STATUS_VALUES,
    TYPOLOGY,
    IdentityStamp,
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


# --- the vocabulary (#137) -------------------------------------------------------------------


def test_an_identity_stamp_refuses_a_status_where_a_fingerprint_is_expected() -> None:
    """
    The defect #137 removes: ``"DONE"`` was a legal ``StampStatus``, so it was a legal write into a
    slot that promises a producer — and a reader could not tell it from an attributed unit.
    """
    for status in sorted(STAMP_STATUS_VALUES):
        with pytest.raises(ValueError, match="producer fingerprint"):
            NER.mark_value({}, status)

    with pytest.raises(ValueError, match="producer fingerprint"):
        NER.mark_value({}, PRODUCER_UNKNOWN)


def test_an_identity_stamp_refuses_a_fingerprint_with_a_trailing_newline() -> None:
    """
    ``$`` matches before a trailing newline in Python but not in PostgreSQL's ``regexp_match``, so
    ``match`` would accept a value the read surface then calls legacy. ``fullmatch`` keeps the write
    path and the report reading the same slot the same way.
    """
    with pytest.raises(ValueError, match="producer fingerprint"):
        NER.mark_value({}, "ab" * 32 + "\n")


def test_an_identity_stamp_writes_a_fingerprint_and_a_failure() -> None:
    """The two things a slot may hold: the identity of a producer, or the plain failure mark."""
    fingerprint = _fingerprint()
    marked = NER.mark_value({"existing": "x"}, fingerprint)

    assert marked == {"existing": "x", NER.key: fingerprint}
    assert NER.mark_failed(marked) == {"existing": "x", NER.key: "ERROR"}


def test_the_legacy_name_is_not_a_fingerprint() -> None:
    """``PRODUCER_UNKNOWN`` has to read as "unknown" to the pattern too, or the report would lie."""
    for stamp in (NER, TYPOLOGY, MACRO_CATEGORY, QUALITY_VALIDATOR, EMBEDDING):
        assert not stamp.fingerprint_pattern.match(PRODUCER_UNKNOWN)


def test_the_embedding_rejects_the_bare_text_hash() -> None:
    """
    The embedding composes the MD5 of the text with the identity. The 4,831 stored rows carry the
    bare MD5 — a text hash that names no producer — so the slot's own pattern is what tells the panel
    they are *not* attributed; a test on ``mark_value`` pins the same expression the panel reads.
    """
    composed = f"{'a' * 32}:{_fingerprint()}"
    assert EMBEDDING.mark_value(None, composed) == {EMBEDDING.key: composed}

    with pytest.raises(ValueError, match="producer fingerprint"):
        EMBEDDING.mark_value(None, "a" * 32)


def test_every_stamped_worker_of_the_catalogue_is_identity_keyed() -> None:
    """A new stamped worker cannot declare a status slot and call it attribution."""
    stamps = [spec.stamp for spec in catalogue.WORKER_CATALOGUE.values() if spec.stamp is not None]

    assert stamps, "the catalogue must stamp at least one worker, or this gate asserts nothing"
    assert all(isinstance(stamp, IdentityStamp) for stamp in stamps)
