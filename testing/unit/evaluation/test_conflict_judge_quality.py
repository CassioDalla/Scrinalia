"""
Unit tests for the conflict-judge bench's arithmetic (issue #114).

The part of the bench that can be wrong in silence runs without a model and without a database: a
failure counted as a verdict, a lopsided gabarito scored as if agreement meant something, a
confusion matrix that loses the direction. These tests build the rows by hand and pin those rules.
"""

from __future__ import annotations

import pytest

from scrinalia.domains.archive.exceptions import EngineExecutionError
from testing.evaluation.conflict_judge_quality import (
    Failed,
    Judged,
    Resolution,
    Verdict,
    agreement,
    confusion,
    constant_baseline,
    parse_config,
    report_for,
    sample,
    score_live,
    worker_auto_resolve_threshold,
    worker_default_config,
)

CENSUS = {"human": 2, "judge": 3, "undone": 1, "total": 6}


def resolution(
    resolution_id: int,
    expected: str = "ENTITY",
    entity_type: str = "LOC",
    source: str = "HUMAN",
) -> Resolution:
    """One ledger row, as ``read_ledger`` returns it — snapshots only, no live id."""
    return Resolution(
        resolution_id=resolution_id,
        tag_name=f"tag-{resolution_id}",
        entity_name=f"entity-{resolution_id}",
        entity_type=entity_type,
        winner=expected,
        source=source,
    )


def judged(row: Resolution, predicted: str = "ENTITY", confidence: float = 0.9, reason: str = "") -> Judged:
    """The judge's answer to one ledger row."""
    return Judged(row, Verdict(winner=predicted, confidence=confidence, reason=reason))


# =============================================================================
# Configurations
# =============================================================================


def test_parse_config_reads_the_registry_names() -> None:
    config = parse_config("ollama_judge:gemma_4b_local")

    assert (config.engine, config.preset, config.label) == (
        "ollama_judge",
        "gemma_4b_local",
        "ollama_judge:gemma_4b_local",
    )


def test_parse_config_accepts_an_engine_without_a_preset() -> None:
    config = parse_config("ollama_judge")

    assert config.preset is None
    assert config.label == "ollama_judge"


def test_parse_config_refuses_an_engine_the_registry_does_not_have() -> None:
    """The judge registry holds one engine; a name it does not have is a bench measuring nothing."""
    with pytest.raises(SystemExit, match="não é um motor do juiz"):
        parse_config("gpt_judge:gemma_4b_local")


def test_parse_config_refuses_a_preset_the_registry_does_not_have() -> None:
    with pytest.raises(SystemExit, match="não é um preset do juiz"):
        parse_config("ollama_judge:llama_70b")


def test_the_worker_default_is_a_configuration_the_registry_accepts() -> None:
    """The default is read from the worker's signature, so it cannot name a model that does not exist."""
    config = parse_config(worker_default_config())

    assert config.engine == "ollama_judge"
    assert config.preset is not None


def test_the_threshold_is_read_from_the_worker() -> None:
    """It is what turns agreement into a decision, so the bench must not carry its own copy."""
    assert worker_auto_resolve_threshold() == 0.85


# =============================================================================
# A failed call is not an opinion
# =============================================================================


def test_a_transport_failure_is_not_a_verdict() -> None:
    """
    The schema has no error state, so a failed call used to come back as ``winner="TAG"`` with
    confidence ``0.0`` — a verdict the model never took. The bench models it as a ``Failed``, which
    is not a ``Judged`` at all: an Ollama outage cannot look like a judge that answers ``TAG`` to
    everything, because it has no verdict to score (#122).
    """
    failed = Failed(resolution(1, expected="ENTITY"), reason="O juiz de conflito não respondeu")
    opinion = judged(resolution(2, expected="ENTITY"), predicted="TAG", confidence=0.4, reason="Regra 3: ambíguo")

    assert isinstance(failed, Failed)
    assert not isinstance(opinion, Failed)
    assert opinion.correct is False


def test_a_failed_pair_leaves_the_score_and_is_reported() -> None:
    """Excluded from the agreement, listed in ``failures``: silent exclusion would hide an outage."""
    rows = [judged(resolution(1, expected="TAG"), predicted="TAG", confidence=1.0)]
    failures = [Failed(resolution(2, expected="ENTITY"), reason="O juiz de conflito não respondeu")]

    report = report_for(parse_config("ollama_judge:gemma_4b_local"), rows, failures, CENSUS, 0.85, 1.0)

    assert report["scored"] == 1
    assert report["failed"] == 1
    assert report["agreement"] == pytest.approx(1.0)
    assert report["failures"][0]["resolution_id"] == 2
    assert report["confusion"] == {"TAG → TAG": 1}
    assert any("fora do placar por falha do motor" in note for note in report["notes"])


def test_an_engine_that_raises_is_counted_as_a_failure_and_not_as_a_verdict(monkeypatch) -> None:
    """The engine raises by contract (#122); the bench counts the exception instead of scoring it."""

    class Exploding:
        def decide_conflict(self, **_kwargs):
            raise EngineExecutionError("O juiz de conflito não respondeu")

    monkeypatch.setattr(
        "testing.evaluation.conflict_judge_quality.get_engine",
        lambda **_kwargs: Exploding(),
    )

    rows, failures, _seconds = score_live(parse_config("ollama_judge:gemma_4b_local"), [resolution(1)])

    assert rows == []
    assert len(failures) == 1
    assert failures[0].resolution.resolution_id == 1
    assert "não respondeu" in failures[0].reason


# =============================================================================
# The constant baseline
# =============================================================================


def test_the_constant_baseline_is_the_most_frequent_verdict() -> None:
    rows = [judged(resolution(i, expected="ENTITY")) for i in range(9)]
    rows.append(judged(resolution(9, expected="TAG")))

    assert constant_baseline(rows) == ("ENTITY", pytest.approx(0.9))


def test_a_judge_that_only_says_entity_scores_zero_above_the_constant() -> None:
    """
    The measured shape of the real ledger: 49 human resolutions, all ``ENTITY``. A judge answering
    only ``ENTITY`` agrees 100% and has measured nothing, which is exactly what Δ exists to say.
    """
    rows = [judged(resolution(i, expected="ENTITY"), predicted="ENTITY") for i in range(49)]

    report = report_for(parse_config("ollama_judge:gemma_4b_local"), rows, [], CENSUS, 0.85, 1.0)

    assert report["agreement"] == pytest.approx(1.0)
    assert report["constant"] == {"label": "ENTITY", "agreement": pytest.approx(1.0), "delta": pytest.approx(0.0)}
    assert any("classe única" in note for note in report["notes"])


def test_a_two_class_gabarito_does_not_carry_the_single_class_note() -> None:
    rows = [judged(resolution(1, expected="TAG")), judged(resolution(2, expected="ENTITY"))]

    report = report_for(parse_config("ollama_judge"), rows, [], CENSUS, 0.85, 1.0)

    assert not any("classe única" in note for note in report["notes"])


# =============================================================================
# The confusion matrix and the auto-resolve split
# =============================================================================


def test_the_confusion_matrix_keeps_the_direction_of_the_mistake() -> None:
    rows = [
        judged(resolution(1, expected="ENTITY"), predicted="ENTITY"),
        judged(resolution(2, expected="ENTITY"), predicted="TAG"),
        judged(resolution(3, expected="TAG"), predicted="ENTITY"),
        judged(resolution(4, expected="TAG"), predicted="TAG"),
    ]

    assert confusion(rows) == {("ENTITY", "ENTITY"): 1, ("ENTITY", "TAG"): 1, ("TAG", "ENTITY"): 1, ("TAG", "TAG"): 1}
    assert agreement(rows) == pytest.approx(0.5)


def test_the_auto_resolve_split_uses_the_workers_own_threshold() -> None:
    """What matters operationally is right *and* sure enough to act without a human."""
    rows = [
        judged(resolution(1, expected="ENTITY"), predicted="ENTITY", confidence=0.99),
        judged(resolution(2, expected="ENTITY"), predicted="TAG", confidence=0.95),
        judged(resolution(3, expected="ENTITY"), predicted="TAG", confidence=0.10),
    ]

    report = report_for(parse_config("ollama_judge"), rows, [], CENSUS, 0.85, 1.0)

    assert report["auto_resolve"] == {
        "resolved": 2,
        "resolved_agreement": pytest.approx(0.5),
        "deferred": 1,
        "deferred_agreement": pytest.approx(0.0),
    }


def test_agreement_by_entity_type_groups_on_the_ledgers_own_column() -> None:
    rows = [
        judged(resolution(1, expected="ENTITY", entity_type="LOC"), predicted="ENTITY"),
        judged(resolution(2, expected="ENTITY", entity_type="LOC"), predicted="TAG"),
        judged(resolution(3, expected="ENTITY", entity_type="PER"), predicted="ENTITY"),
    ]

    report = report_for(parse_config("ollama_judge"), rows, [], CENSUS, 0.85, 1.0)

    assert report["entity_types"] == [
        {"entity_type": "LOC", "rows": 2, "agreement": pytest.approx(0.5)},
        {"entity_type": "PER", "rows": 1, "agreement": pytest.approx(1.0)},
    ]


def test_an_empty_score_is_reported_as_empty_and_not_as_zero() -> None:
    """A run where the engine answered nothing is not a judge that got everything wrong."""
    report = report_for(parse_config("ollama_judge"), [], [], CENSUS, 0.85, 0.0)

    assert report["scored"] == 0
    assert any("Nada foi pontuado" in note for note in report["notes"])


# =============================================================================
# The trial subset
# =============================================================================


def test_sample_returns_everything_when_the_limit_does_not_bite() -> None:
    rows = [resolution(i) for i in range(1, 6)]

    assert sample(rows, "s", None) == rows
    assert sample(rows, "s", 5) == rows


def test_sample_is_deterministic_and_keeps_the_ledger_order() -> None:
    """The subset is drawn by hash and not by position: the ledger is ordered by decision time."""
    rows = [resolution(i) for i in range(1, 51)]

    first = sample(rows, "seed", 10)
    again = sample(rows, "seed", 10)

    assert first == again
    assert len(first) == 10
    assert [row.resolution_id for row in first] == sorted(row.resolution_id for row in first)


def test_sample_of_a_different_seed_draws_a_different_subset() -> None:
    rows = [resolution(i) for i in range(1, 51)]

    assert sample(rows, "a", 10) != sample(rows, "b", 10)


def test_sample_refuses_a_non_positive_limit() -> None:
    with pytest.raises(SystemExit):
        sample([resolution(1)], "seed", 0)
