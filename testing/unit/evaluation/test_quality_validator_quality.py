"""
Unit tests for the quality-validator bench's arithmetic (issue #115).

The part of the bench that can be wrong in silence runs without a database and without a model: a
false positive counted as a miss, a rule the curator never mentions vanishing from the table, a
gabarito naming a rule the catalogue does not have read as a guarantee of failure. These tests build
the rows by hand and pin those rules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrinalia.domains.archive.schemas.cleaning_schema import CleaningRuleDTO
from testing.evaluation import MIN_POSITIVES
from testing.evaluation.quality_validator_quality import (
    CLEAN,
    NO_RULE,
    Candidate,
    LabelledRow,
    Scored,
    ambiguous_rules,
    flag_agreement,
    load_labelled,
    load_payload,
    order_key,
    pick,
    report_for,
    scorable_rules,
    score_rules,
    stored_key,
)


def rule(
    name: str,
    kind: str = "VALIDATE",
    *,
    active: bool = True,
    anomaly_reason: str | None = None,
    rule_id: int = 1,
) -> CleaningRuleDTO:
    """One catalogue rule, with only the fields the bench reads."""
    return CleaningRuleDTO(
        rule_id=rule_id,
        rule_name=name,
        target_column="original_title",
        regex_pattern="x",
        replacement_string="",
        rule_kind=kind,  # type: ignore[arg-type]
        anomaly_reason=anomaly_reason,
        is_active=active,
    )


def row(expected: list[str], predicted: list[str], needs_decision: bool = False) -> Scored:
    return Scored(
        description_id=f"doc-{expected}-{predicted}",
        expected=frozenset(expected),
        predicted=frozenset(predicted),
        needs_decision=needs_decision,
    )


# =============================================================================
# Which rules are measured
# =============================================================================


def test_scorable_rules_keeps_the_flags_and_drops_the_rewrites() -> None:
    """A REWRITE rule changes the text and marks nothing: there is no flag to agree with."""
    rules = [rule("reescreve", "REWRITE"), rule("sinaliza", "VALIDATE"), rule("modelo", "LLM_CHECK")]

    assert [item.rule_name for item in scorable_rules(rules)] == ["sinaliza", "modelo"]


def test_scorable_rules_drops_the_retired_ones() -> None:
    assert scorable_rules([rule("aposentada", active=False)]) == []


def test_ambiguous_rules_names_a_duplicated_rule_name() -> None:
    problems = ambiguous_rules([rule("repetida", rule_id=1), rule("repetida", rule_id=2)])

    assert problems and "repetida" in problems[0]


def test_ambiguous_rules_names_two_validate_rules_sharing_a_flag_label() -> None:
    """A flag carries ``anomaly_reason or rule_name``: two rules sharing it cannot be told apart."""
    rules = [rule("a", anomaly_reason="mesmo motivo", rule_id=1), rule("b", anomaly_reason="mesmo motivo", rule_id=2)]

    problems = ambiguous_rules(rules)

    assert problems and "mesmo motivo" in problems[0]


def test_an_unambiguous_catalogue_has_no_problems() -> None:
    assert ambiguous_rules([rule("a", rule_id=1), rule("b", "LLM_CHECK", rule_id=2)]) == []


# =============================================================================
# Per-rule precision and recall
# =============================================================================


def test_score_rules_counts_each_direction_of_the_mistake() -> None:
    rules = [rule("rua")]
    rows = [
        row(["rua"], ["rua"]),  # true positive
        row(["rua"], []),  # missed: the anomaly it should have caught
        row([], ["rua"]),  # spurious: the flag it should not have raised
    ]

    (score,) = score_rules(rows, rules)

    assert (score.true_positives, score.false_positives, score.false_negatives) == (1, 1, 1)
    assert score.support == 2
    assert score.fired == 2
    assert score.precision == pytest.approx(0.5)
    assert score.recall == pytest.approx(0.5)
    assert score.f1 == pytest.approx(0.5)


def test_a_rule_that_never_fires_has_zero_recall_and_is_still_reported() -> None:
    """Silence in the table would read as a rule that works; the zero is the finding."""
    (score,) = score_rules([row(["rua"], [])], [rule("rua")])

    assert score.fired == 0
    assert score.recall == pytest.approx(0.0)
    assert score.precision == pytest.approx(0.0)


def test_a_rule_the_curator_never_mentions_gets_a_line() -> None:
    """On a set of forty documents, "this rule agrees with nobody" is a result, not an absence."""
    scores = score_rules([row([], [])], [rule("silenciosa")])

    assert [score.label for score in scores] == ["silenciosa"]
    assert scores[0].support == 0
    assert scores[0].fired == 0


def test_a_rule_below_the_support_floor_is_not_measured() -> None:
    """The floor the typology bench uses, on the same quantity: the positives the curator gave."""
    rules = [rule("rara"), rule("comum")]
    rows = [row(["rara"], ["rara"])] + [row(["comum"], ["comum"]) for _ in range(MIN_POSITIVES)]
    by_label = {score.label: score for score in score_rules(rows, rules)}

    assert not by_label["rara"].measured
    assert by_label["comum"].measured


def test_rows_marked_needs_decision_leave_the_placar() -> None:
    """
    The ambiguity belongs to the catalogue, so the row is counted apart and not scored.

    The filter lives in ``report_for`` and not in ``score_rules``, which is why this test goes
    through the report: an ``expected`` list that the catalogue cannot express must not become a
    false negative against a rule that was never allowed to satisfy it.
    """
    report = report_for(
        "live",
        [row(["rua"], ["rua"]), row(["rua"], [], needs_decision=True)],
        [rule("rua")],
        labelled=2,
        missing_from_collection=0,
    )

    assert report["scored"] == 1
    assert report["needs_decision"] == 1
    assert report["rules"][0]["false_negatives"] == 0
    assert any("ambiguidade pertence ao catálogo" in note for note in report["notes"])


def test_the_report_says_so_when_no_rule_reaches_the_floor() -> None:
    """Two examples produce an F1 that reads like a measurement; the report refuses to print one."""
    report = report_for("live", [row(["rua"], ["rua"])], [rule("rua")], labelled=1, missing_from_collection=0)

    assert report["unmeasured"] == ["rua"]
    assert any("piso de" in note for note in report["notes"])


def test_the_report_counts_the_rows_the_collection_lost() -> None:
    report = report_for("live", [row(["rua"], ["rua"])], [rule("rua")], labelled=3, missing_from_collection=2)

    assert report["missing_from_collection"] == 2
    assert any("não existem mais na coleção" in note for note in report["notes"])


def test_the_order_is_by_support_then_firings_then_name() -> None:
    rules = [rule("z", rule_id=1), rule("a", rule_id=2)]
    rows = [row(["a"], ["a"]), row(["z"], [])]

    assert [score.label for score in score_rules(rows, rules)] == ["a", "z"]


# =============================================================================
# The whole flag set
# =============================================================================


def test_flag_agreement_wants_the_whole_set_not_only_the_intersection() -> None:
    """A document the validator got half right is not a document it got right."""
    assert flag_agreement([row(["a"], ["a"]), row(["a", "b"], ["a"])]) == pytest.approx(0.5)
    assert flag_agreement([row([], [])]) == pytest.approx(1.0)


def test_flag_agreement_of_nothing_is_zero_and_not_a_division_error() -> None:
    assert flag_agreement([]) == 0.0


# =============================================================================
# The strata of the picker
# =============================================================================


LABELS = {"motivo gravado": "regra"}


def test_stored_key_reads_the_labels_the_worker_writes() -> None:
    assert stored_key(["RULE_MATCH:motivo gravado"], LABELS, []) == "regra"
    assert stored_key(["RULE_MATCH:outro"], LABELS, []) == NO_RULE


def test_stored_key_sends_the_llm_flag_to_the_llm_rule() -> None:
    assert stored_key(["LLM_SUSPECT:o modelo achou estranho"], LABELS, ["revisor"]) == "revisor"


def test_stored_key_needs_a_rule_for_the_llm_flag_to_land_somewhere() -> None:
    """With no LLM_CHECK rule active, the stored flag belongs to no rule being measured."""
    assert stored_key(["LLM_SUSPECT:texto livre"], LABELS, []) == NO_RULE


def test_stored_key_separates_clean_documents_from_the_ones_something_touched() -> None:
    assert stored_key([], LABELS, []) == CLEAN
    assert stored_key(["NO_TAGS"], LABELS, []) == NO_RULE


def candidate(description_id: str, title: str, key: str) -> Candidate:
    return Candidate(description_id=description_id, title=title, stored_reasons=(), key=key)


def test_pick_is_deterministic_and_bounded_by_each_stratum() -> None:
    rows = [candidate(str(index), f"titulo {index}", "regra") for index in range(10)]
    rows += [candidate("c1", "limpo", CLEAN), candidate("c2", "limpo tambem", CLEAN)]

    first = pick(rows, ["regra"], "seed", 4, 1)
    again = pick(rows, ["regra"], "seed", 4, 1)

    assert first == again
    assert len(first["regra"]) == 4
    assert len(first[CLEAN]) == 1


def test_pick_deduplicates_by_the_title_the_rules_read() -> None:
    """Two documents with the same title cannot disagree, and the second would weight the repeat."""
    rows = [candidate("a", "Rua XV", "regra"), candidate("b", "rua xv", "regra")]

    picked = pick(rows, ["regra"], "seed", 10, 0)

    assert len(picked["regra"]) == 1


def test_order_key_is_the_same_for_the_same_pair() -> None:
    assert order_key("seed", "1") == order_key("seed", "1")
    assert order_key("seed", "1") != order_key("seed", "2")


# =============================================================================
# The labelled set
# =============================================================================


def write_pairs(tmp_path: Path, pairs: list[dict], status: str = "aprovado pelo curador em 2026-10-17") -> Path:
    path = tmp_path / "validator_pairs.json"
    path.write_text(json.dumps({"pairs": pairs, "status": status}, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_labelled_refuses_a_set_nobody_signed(tmp_path) -> None:
    path = write_pairs(tmp_path, [{"description_id": "a", "expected": ["rua"]}], status="draft — nada revisado")

    with pytest.raises(SystemExit, match="rascunho"):
        load_labelled(path, ["rua"], allow_draft=False)


def test_load_labelled_accepts_a_draft_with_the_flag(tmp_path) -> None:
    path = write_pairs(tmp_path, [{"description_id": "a", "expected": ["rua"]}], status="draft")

    rows, _payload = load_labelled(path, ["rua"], allow_draft=True)

    assert rows[0].expected == frozenset({"rua"})


def test_an_empty_expected_is_the_answer_that_measures_precision(tmp_path) -> None:
    """'No rule should have flagged this document' is a verdict, not a missing field."""
    path = write_pairs(tmp_path, [{"description_id": "a", "expected": []}])

    rows, _payload = load_labelled(path, ["rua"], allow_draft=False)

    assert rows[0].expected == frozenset()


def test_load_labelled_refuses_a_rule_the_catalogue_does_not_have(tmp_path) -> None:
    """It is a guaranteed miss the rule cannot avoid, and a typo far more often than a retired rule."""
    path = write_pairs(tmp_path, [{"description_id": "a", "expected": ["inexistente"]}])

    with pytest.raises(SystemExit, match="catálogo ativo não tem"):
        load_labelled(path, ["rua"], allow_draft=False)


def test_load_labelled_refuses_an_expected_that_is_not_a_list(tmp_path) -> None:
    path = write_pairs(tmp_path, [{"description_id": "a", "expected": "rua"}])

    with pytest.raises(SystemExit, match="lista de nomes"):
        load_labelled(path, ["rua"], allow_draft=False)


def test_load_labelled_refuses_a_confidence_outside_the_vocabulary(tmp_path) -> None:
    path = write_pairs(tmp_path, [{"description_id": "a", "expected": [], "confidence": "altíssima"}])

    with pytest.raises(SystemExit, match="confidence"):
        load_labelled(path, ["rua"], allow_draft=False)


def test_labelled_row_reads_the_note_and_the_flag() -> None:
    row_read = LabelledRow(description_id="a", expected=frozenset(), needs_decision=True, note="catálogo ambíguo")

    assert row_read.needs_decision
    assert row_read.note == "catálogo ambíguo"


def test_load_payload_says_what_to_do_when_the_set_does_not_exist(tmp_path) -> None:
    """The reflex fix for a missing fixture is to recreate it from the code, which must not happen."""
    with pytest.raises(SystemExit, match="não são versionadas"):
        load_payload(tmp_path / "ausente.json")


def test_load_payload_refuses_a_file_that_is_not_json(tmp_path) -> None:
    path = tmp_path / "quebrado.json"
    path.write_text("{ nao e json", encoding="utf-8")

    with pytest.raises(SystemExit, match="não é um JSON válido"):
        load_payload(path)


def test_load_payload_refuses_a_json_that_is_not_an_object(tmp_path) -> None:
    path = tmp_path / "lista.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(SystemExit, match="objeto JSON"):
        load_payload(path)
