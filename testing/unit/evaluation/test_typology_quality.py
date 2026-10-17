"""
Unit tests for the typology bench's metrics (issue #69).

The arithmetic is the part of the bench that can be wrong in silence: it runs without a model and
without a database, so nothing in a manual run would notice precision and recall swapped. These
tests build the rows by hand and pin the rules the report depends on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from testing.evaluation.typology_quality import (
    ABSTAINED,
    LabelledRow,
    Prediction,
    Scored,
    Truth,
    abstention_rate,
    agreement,
    allocate,
    confusion,
    entropy_bits,
    largest_share,
    link_decision,
    load_labelled,
    macro_f1,
    parse_config,
    per_class,
    unknown_truth_labels,
)

DEFAULT_COLUMNS = ("original_title",)
DEFAULT_THRESHOLD = 0.40


def scored(expected: str | list[str] | None, predicted: str | None, score: float | None = None) -> Scored:
    """One row of the bench: the curator's truth and the classifier's answer."""
    labels = None if expected is None else frozenset([expected] if isinstance(expected, str) else expected)
    return Scored(
        description_id=f"doc-{expected}-{predicted}",
        truth=Truth(labels=labels),
        prediction=Prediction(label=predicted, score=score),
    )


# =============================================================================
# Agreement, abstention and the NENHUMA class
# =============================================================================


def test_a_none_row_is_right_only_when_the_classifier_abstains() -> None:
    """``expected: null`` means no typology applies, so answering one is an error, not a bonus."""
    right = scored(None, None)
    wrong = scored(None, "Fotografia")

    assert right.correct
    assert not wrong.correct


def test_an_acceptable_list_is_right_when_the_answer_is_any_of_them() -> None:
    """The catalogue mixes support and species; both answers are legitimate and neither is a miss."""
    row = scored(["Mapa / Croqui Urbanístico", "Planta Arquitetônica"], "Mapa / Croqui Urbanístico")

    assert row.correct
    assert not scored(["Mapa / Croqui Urbanístico", "Planta Arquitetônica"], "Fotografia").correct


def test_agreement_and_abstention_rate_count_the_abstention_as_a_prediction() -> None:
    rows = [
        scored("Fotografia", "Fotografia"),
        scored("Fotografia", None),
        scored(None, None),
        scored(None, "Fotografia"),
    ]

    assert agreement(rows) == pytest.approx(0.5)
    assert abstention_rate(rows) == pytest.approx(0.5)


def test_agreement_of_an_empty_run_is_zero_and_not_a_division_error() -> None:
    assert agreement([]) == 0.0
    assert abstention_rate([]) == 0.0


def test_confusion_names_the_abstention_bucket() -> None:
    """A dropped answer and a wrong answer are different failures; the matrix must tell them apart."""
    cells = confusion([scored("Fotografia", None), scored("Fotografia", "Planta Arquitetônica")])

    assert cells[("Fotografia", ABSTAINED)] == 1
    assert cells[("Fotografia", "Planta Arquitetônica")] == 1


# =============================================================================
# Per-class metrics
# =============================================================================


def test_per_class_treats_an_any_of_truth_as_multi_label() -> None:
    """
    An acceptable list gives the predicted label a true positive and the other one a false negative.

    Both readings are true at once: the model found one of the two forms the curator accepts, and it
    did not find the other. Collapsing them into one column would hide which one it can find.
    """
    rows = [scored(["Mapa / Croqui Urbanístico", "Planta Arquitetônica"], "Planta Arquitetônica")]

    metrics = per_class(rows, ["Mapa / Croqui Urbanístico", "Planta Arquitetônica"], min_positives=1)

    assert metrics["Planta Arquitetônica"].true_positives == 1
    assert metrics["Planta Arquitetônica"].false_negatives == 0
    assert metrics["Mapa / Croqui Urbanístico"].true_positives == 0
    assert metrics["Mapa / Croqui Urbanístico"].false_negatives == 1


def test_precision_recall_and_f1_of_a_hand_built_confusion() -> None:
    rows = [
        scored("A", "A"),
        scored("A", "B"),
        scored("B", "B"),
        scored("B", "A"),
    ]

    metrics = per_class(rows, ["A", "B"], min_positives=1)

    for label in ("A", "B"):
        assert metrics[label].support == 2
        assert metrics[label].precision == pytest.approx(0.5)
        assert metrics[label].recall == pytest.approx(0.5)
        assert metrics[label].f1 == pytest.approx(0.5)


def test_a_class_below_the_floor_is_not_measured_and_leaves_macro_f1() -> None:
    """Two examples produce a number that reads like a measurement; the floor keeps it out."""
    rows = [scored("Raro", "Raro"), scored("Comum", "Comum"), scored("Comum", "Comum")]

    metrics = per_class(rows, ["Raro", "Comum"], min_positives=2)

    assert not metrics["Raro"].measured
    assert metrics["Comum"].measured
    assert macro_f1(metrics) == pytest.approx(1.0)
    assert macro_f1(per_class(rows, ["Raro", "Comum"], min_positives=10)) == 0.0


# =============================================================================
# Distribution: the collapse, as a number
# =============================================================================


def test_a_collapse_shows_as_share_one_and_entropy_zero() -> None:
    """The defect that opened the issue was 78 of 92 answers in one drawer, not a low score."""
    from collections import Counter

    counts = Counter({"Planta Arquitetônica": 10})

    assert largest_share(counts) == ("Planta Arquitetônica", pytest.approx(1.0))
    assert entropy_bits(counts) == pytest.approx(0.0)


def test_a_uniform_spread_has_maximum_entropy() -> None:
    from collections import Counter

    counts = Counter({"A": 1, "B": 1, "C": 1, "D": 1})

    assert largest_share(counts)[1] == pytest.approx(0.25)
    assert entropy_bits(counts) == pytest.approx(2.0)


def test_entropy_of_nothing_is_zero() -> None:
    from collections import Counter

    assert entropy_bits(Counter()) == 0.0


# =============================================================================
# Configuration parsing
# =============================================================================


def test_parse_config_fills_the_empty_fields_from_the_worker() -> None:
    config = parse_config("deberta_typology", DEFAULT_COLUMNS, DEFAULT_THRESHOLD)

    assert config.preset is None
    assert config.columns == DEFAULT_COLUMNS
    assert config.threshold == DEFAULT_THRESHOLD


def test_parse_config_reads_all_four_fields() -> None:
    config = parse_config("deberta_typology:gpu_cloud:original_title,scope_content:0.55", DEFAULT_COLUMNS, 0.40)

    assert config.engine == "deberta_typology"
    assert config.preset == "gpu_cloud"
    assert config.columns == ("original_title", "scope_content")
    assert config.threshold == pytest.approx(0.55)
    assert config.label == "deberta_typology:gpu_cloud:original_title,scope_content:0.55"


def test_parse_config_refuses_an_unknown_column() -> None:
    with pytest.raises(SystemExit):
        parse_config("deberta_typology:cpu_local:nao_existe", DEFAULT_COLUMNS, DEFAULT_THRESHOLD)


def test_parse_config_refuses_more_fields_than_it_has() -> None:
    with pytest.raises(SystemExit):
        parse_config("a:b:c:0.4:extra", DEFAULT_COLUMNS, DEFAULT_THRESHOLD)


def test_parse_config_refuses_a_threshold_that_is_not_a_number() -> None:
    with pytest.raises(SystemExit):
        parse_config("deberta_typology:cpu_local:original_title:alto", DEFAULT_COLUMNS, DEFAULT_THRESHOLD)


# =============================================================================
# The collection sample (issue #109)
# =============================================================================


def test_link_decision_links_strictly_above_the_floor() -> None:
    """
    The worker's comparison is ``>``, and the bench abstaining on an equal score is the difference
    between the abstention rate it prints and the one the run produces.
    """
    answer = {"labels": ["Fotografia"], "scores": [0.40]}

    assert link_decision(answer, 0.40).label is None
    assert link_decision(answer, 0.39).label == "Fotografia"
    assert link_decision(answer, 0.40).score == pytest.approx(0.40)


def test_allocate_is_proportional_and_adds_up() -> None:
    """The sample has to weigh the strata the way the collection does, and land on ``total``."""
    counts = {"Fotografia": 3164, "Planta Arquitetônica": 1589, "NENHUMA": 22, "Audiovisual": 1}

    allocation = allocate(counts, 100)

    assert sum(allocation.values()) == 100
    # 98,3% of the collection is the two dominant strata, and the sample says the same.
    assert allocation["Fotografia"] + allocation["Planta Arquitetônica"] >= 97
    # The leftover seat follows the largest fractional part — NENHUMA (0,46) and not the smallest
    # stratum — so the rule is a remainder and not a floor. Pinned because a "fix" that made it a
    # floor would inflate the projected hours without changing anything the sample prints.
    assert allocation["NENHUMA"] == 1
    assert "Audiovisual" not in allocation


def test_allocate_gives_the_rare_forms_no_floor() -> None:
    """
    A floor of one row per stratum would hand 6% of a 100-row sample to forms that are 0,85% of the
    collection — and those are the forms with the longest texts, so the projected hours would grow
    with a distortion and not with the collection.
    """
    allocation = allocate({"Fotografia": 4000, "Processo Administrativo": 6}, 100)

    assert allocation == {"Fotografia": 100}


def test_allocate_of_an_empty_or_zero_sample_is_empty() -> None:
    assert allocate({}, 100) == {}
    assert allocate({"Fotografia": 10}, 0) == {}


# =============================================================================
# The labelled set
# =============================================================================


def write_pairs(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "typology_pairs.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def payload_with(expected, status="aprovado pelo curador em 2026-10-15") -> dict:
    return {
        "pairs": [{"description_id": "doc-1", "expected": expected}],
        "status": status,
    }


def test_load_labelled_refuses_a_set_nobody_signed(tmp_path) -> None:
    """A draft produces a figure that reads exactly like a reviewed one; the gate is the point."""
    path = write_pairs(tmp_path, payload_with("Fotografia", status="draft — nenhum curador revisou"))

    with pytest.raises(SystemExit):
        load_labelled(path, ["Fotografia"], allow_draft=False)


def test_load_labelled_accepts_a_draft_with_the_flag(tmp_path) -> None:
    path = write_pairs(tmp_path, payload_with("Fotografia", status="draft"))

    rows, _payload = load_labelled(path, ["Fotografia"], allow_draft=True)

    assert rows[0].truth.labels == frozenset({"Fotografia"})


def test_load_labelled_reads_a_list_and_a_null(tmp_path) -> None:
    payload = {
        "pairs": [
            {"description_id": "a", "expected": ["Fotografia", "Audiovisual"], "confidence": "baixa"},
            {"description_id": "b", "expected": None, "needs_decision": True, "note": "catálogo ambíguo"},
        ],
        "status": "aprovado",
    }
    path = write_pairs(tmp_path, payload)

    rows, _payload = load_labelled(path, ["Fotografia", "Audiovisual"], allow_draft=False)

    assert rows[0].truth.labels == frozenset({"Fotografia", "Audiovisual"})
    assert rows[1].truth.is_none
    assert rows[1].needs_decision


def test_load_labelled_refuses_an_expected_that_is_neither_name_nor_list_nor_null(tmp_path) -> None:
    path = write_pairs(tmp_path, payload_with(7))

    with pytest.raises(SystemExit):
        load_labelled(path, ["Fotografia"], allow_draft=False)


def test_load_labelled_refuses_a_confidence_outside_the_vocabulary(tmp_path) -> None:
    payload = payload_with("Fotografia")
    payload["pairs"][0]["confidence"] = "altíssima"
    path = write_pairs(tmp_path, payload)

    with pytest.raises(SystemExit):
        load_labelled(path, ["Fotografia"], allow_draft=False)


def test_unknown_truth_labels_names_the_retired_typology() -> None:
    """A label the catalogue retired is a guaranteed miss, and the curator has to see it."""
    rows = [
        LabelledRow(description_id="a", truth=Truth(labels=frozenset({"Fotografia"})), needs_decision=False, note=""),
        LabelledRow(
            description_id="b", truth=Truth(labels=frozenset({"Dossiê Funcional"})), needs_decision=False, note=""
        ),
    ]

    assert unknown_truth_labels(rows, ["Fotografia"]) == ["Dossiê Funcional"]
