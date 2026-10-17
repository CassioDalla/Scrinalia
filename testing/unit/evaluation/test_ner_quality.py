"""
Unit tests for the NER bench's metrics (issue #113).

The arithmetic is the part of the bench that can be wrong in silence: it runs without a model and
without a database, so nothing in a manual run would notice precision and recall swapped, or a
boundary miss counted as a hit. These tests build the mentions by hand and pin the rules the report
depends on.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from testing.evaluation.ner_quality import (
    ENTITY_TYPES,
    NO_TYPE,
    OVERALL,
    BenchConfig,
    Candidate,
    Extraction,
    Mention,
    ScoredRow,
    Truth,
    agreement,
    boundary_breakdown,
    empty_rate,
    entropy_bits,
    largest_share,
    load_labelled,
    macro_f1,
    match_mentions,
    parse_config,
    per_type,
    report_for,
    scorable_rows,
    type_distribution,
)


def mention(term: str, entity_type: str) -> Mention:
    return Mention(term=term, type=entity_type)


def row(description_id: str, gold: list[Mention], predicted: list[Mention]) -> ScoredRow:
    return ScoredRow(
        description_id=description_id,
        truth=Truth(mentions=tuple(gold)),
        extraction=Extraction(mentions=tuple(predicted)),
    )


# =============================================================================
# The pairing: which bucket a mention lands in
# =============================================================================


def test_a_term_with_the_right_string_and_type_is_a_hit() -> None:
    match = match_mentions([mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")])

    assert len(match.hits) == 1
    assert not match.boundary
    assert not match.missing
    assert not match.spurious


def test_the_comparison_ignores_case_and_extra_whitespace() -> None:
    """The engine title-cases what it returns; the curator types what they read."""
    match = match_mentions([mention("curitiba", "LOC")], [mention("  Curitiba ", "LOC")])

    assert len(match.hits) == 1


def test_a_prediction_longer_than_the_gold_is_a_boundary_miss() -> None:
    """The token-boundary defect of #69: the entity was found, the span starts or ends wrong."""
    match = match_mentions([mention("Curitiba", "LOC")], [mention("Curitiba - Paraná", "LOC")])

    assert len(match.boundary) == 1
    assert not match.missing
    assert not match.spurious


def test_a_prediction_shorter_than_the_gold_is_a_boundary_miss() -> None:
    """The other direction, and the common one: the model stops the span too early."""
    match = match_mentions([mention("Curitiba - Paraná", "LOC")], [mention("Curitiba", "LOC")])

    assert len(match.boundary) == 1


def test_a_reordered_term_is_a_missing_term_and_not_a_boundary_miss() -> None:
    """
    "Silva, João" is not a span of "João Silva": the tokens are not a contiguous run.

    Calling it a boundary error would credit the model for finding an entity it found in the wrong
    order, which is a different defect and one the measure must not absorb.
    """
    match = match_mentions([mention("João Silva", "PER")], [mention("Silva, João", "PER")])

    assert not match.boundary
    assert len(match.missing) == 1
    assert len(match.spurious) == 1


def test_a_shared_token_that_is_not_a_contiguous_run_is_not_a_boundary() -> None:
    match = match_mentions([mention("Rua XV de Novembro", "LOC")], [mention("Rua de Novembro", "LOC")])

    assert not match.boundary
    assert len(match.missing) == 1


def test_a_term_found_with_the_wrong_type_is_a_type_confusion() -> None:
    """
    Neither a boundary error nor a term the model failed to see, and it used to disappear.

    Folding it into "missing" would report a term the engine clearly extracted as one it never saw.
    """
    match = match_mentions([mention("Curitiba", "LOC")], [mention("Curitiba", "ORG")])

    assert len(match.type_confusions) == 1
    assert not match.boundary
    assert not match.missing
    assert not match.spurious


def test_the_same_string_with_a_different_type_is_not_a_boundary_miss() -> None:
    """The boundary rule compares token runs, and equal strings are not a boundary problem."""
    match = match_mentions([mention("Curitiba", "LOC")], [mention("Curitiba", "PER")])

    assert not match.boundary
    assert len(match.type_confusions) == 1


def test_a_term_nobody_found_is_missing_and_an_extra_one_is_spurious() -> None:
    match = match_mentions([mention("Curitiba", "LOC")], [mention("Paraná", "LOC")])

    assert [seen.term for seen in match.missing] == ["Curitiba"]
    assert [seen.term for seen in match.spurious] == ["Paraná"]


def test_the_pairing_is_one_to_one() -> None:
    """Two predictions of the same term cannot both answer one gold mention."""
    match = match_mentions([mention("Curitiba", "LOC")], [mention("Curitiba", "LOC"), mention("Curitiba", "LOC")])

    assert len(match.hits) == 1
    assert len(match.spurious) == 1


def test_the_pairing_does_not_depend_on_the_order_the_rows_were_written_in() -> None:
    """A set re-ordered by hand must not produce a different score."""
    gold = [mention("Curitiba", "LOC"), mention("David Carneiro", "PER")]
    first = match_mentions(gold, [mention("Curitiba", "LOC"), mention("David Carneiro", "PER")])
    second = match_mentions(
        list(reversed(gold)), list(reversed([mention("Curitiba", "LOC"), mention("David Carneiro", "PER")]))
    )

    assert first == second


# =============================================================================
# Precision, recall and F1 — exact match is the rule
# =============================================================================


def test_precision_and_recall_are_exact_match() -> None:
    """
    A boundary miss is one false negative **and** one false positive.

    The gold asked for two terms; one was returned exactly and one was returned with the wrong span.
    Under the exact rule the engine got one right and produced two outputs, so both numbers are 0.5 —
    and a reader who sees only "recall 0.5" would think the term was not found at all.
    """
    rows = [
        row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]),
        row("b", [mention("Paraná", "LOC")], [mention("Paraná - Sul", "LOC")]),
    ]

    loc = per_type(rows, ENTITY_TYPES, min_positives=1)["LOC"]

    assert loc.support == 2
    assert loc.true_positives == 1
    assert loc.false_positives == 1
    assert loc.false_negatives == 1
    assert loc.recall == pytest.approx(0.5)
    assert loc.precision == pytest.approx(0.5)
    assert loc.f1 == pytest.approx(0.5)


def test_the_relaxed_recall_counts_the_boundary_and_never_replaces_the_exact_one() -> None:
    rows = [
        row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]),
        row("b", [mention("Paraná", "LOC")], [mention("Paraná - Sul", "LOC")]),
    ]

    loc = per_type(rows, ENTITY_TYPES, min_positives=1)["LOC"]

    assert loc.recall == pytest.approx(0.5)
    assert loc.relaxed_recall == pytest.approx(1.0)


def test_a_type_confusion_costs_the_gold_type_a_miss_and_the_other_a_false_positive() -> None:
    """The two types are different rows, and crediting both is what makes the table add up."""
    rows = [row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "ORG")])]

    metrics = per_type(rows, ENTITY_TYPES, min_positives=1)

    assert metrics["LOC"].support == 1
    assert metrics["LOC"].true_positives == 0
    assert metrics["LOC"].type_confusions == 0  # the miss belongs to LOC, the extra output to ORG
    assert metrics["LOC"].false_negatives == 1
    assert metrics["ORG"].support == 0
    assert metrics["ORG"].false_positives == 1
    assert metrics["ORG"].precision == 0.0


def test_a_spurious_term_costs_precision_only() -> None:
    rows = [row("a", [], [mention("Curitiba", "LOC")])]

    loc = per_type(rows, ENTITY_TYPES, min_positives=1)["LOC"]

    assert loc.support == 0
    assert loc.false_positives == 1
    assert loc.precision == 0.0


def test_the_overall_row_sums_the_types() -> None:
    rows = [
        row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]),
        row("b", [mention("David Carneiro", "PER")], []),
    ]

    overall = per_type(rows, ENTITY_TYPES, min_positives=1)[OVERALL]

    assert overall.support == 2
    assert overall.true_positives == 1
    assert overall.false_negatives == 1
    assert overall.recall == pytest.approx(0.5)


def test_a_type_below_the_support_floor_is_not_measured() -> None:
    """An F1 built on two rows reads like a measurement and is not one."""
    rows = [row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")])]

    loc = per_type(rows, ENTITY_TYPES, min_positives=5)["LOC"]

    assert loc.support == 1
    assert not loc.measured


def test_macro_f1_ignores_a_type_that_was_not_measured() -> None:
    """
    A type below the floor is absent from the mean, not a zero in it.

    LOC has six labelled mentions and finds them all; PER has one and finds nothing. Counting PER as
    a zero would report macro-F1 0.500 for an extractor that is perfect on everything the set can
    actually measure.
    """
    rows = [row(f"loc{index}", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]) for index in range(6)]
    rows.append(row("per1", [mention("David Carneiro", "PER")], []))

    metrics = per_type(rows, ENTITY_TYPES, min_positives=5)

    assert metrics["LOC"].measured
    assert not metrics["PER"].measured
    assert macro_f1(metrics) == pytest.approx(1.0)


def test_the_overall_row_is_always_printed_even_below_the_floor() -> None:
    """The floor is about a rare *class*; the aggregate over the whole set is not a rare class."""
    rows = [row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")])]

    overall = per_type(rows, ENTITY_TYPES, min_positives=5)[OVERALL]

    assert overall.support == 1
    assert overall.precision == pytest.approx(1.0)


def test_macro_f1_is_the_mean_over_the_measured_types() -> None:
    rows = [
        row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]),
        row("b", [mention("David Carneiro", "PER")], [mention("David Carneiro", "PER")]),
    ]

    metrics = per_type(rows, ENTITY_TYPES, min_positives=1)

    assert macro_f1(metrics) == pytest.approx(1.0)


# =============================================================================
# The boundary breakdown, as counts
# =============================================================================


def test_the_breakdown_partitions_the_gold() -> None:
    """
    Every expected mention is exactly one of hit, boundary, type confusion or missing.

    The four adding up to the support is what lets a reader check the arithmetic instead of trusting
    it — and it is the property that would break first if a new bucket were added carelessly.
    """
    rows = [
        row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]),
        row("b", [mention("Paraná", "LOC")], [mention("Paraná - Sul", "LOC")]),
        row("c", [mention("David Carneiro", "PER")], [mention("David Carneiro", "ORG")]),
        row("d", [mention("Araucária", "LOC")], []),
    ]

    counts = boundary_breakdown(rows)
    gold = sum(len(entry.truth.mentions) for entry in rows)

    assert counts["hits"] == 1
    assert counts["boundary"] == 1
    assert counts["type_confusions"] == 1
    assert counts["missing"] == 1
    assert counts["hits"] + counts["boundary"] + counts["type_confusions"] + counts["missing"] == gold


def test_the_breakdown_counts_a_spurious_term_apart_from_the_gold() -> None:
    """A spurious term is not part of the partition: nothing in the gold asked for it."""
    rows = [row("a", [], [mention("Curitiba", "LOC")])]

    counts = boundary_breakdown(rows)

    assert counts["spurious"] == 1
    assert counts["hits"] == counts["boundary"] == counts["missing"] == 0


# =============================================================================
# Documents, distributions and the collapse detector
# =============================================================================


def test_a_document_is_correct_only_under_the_exact_rule() -> None:
    assert row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]).correct
    assert not row("a", [mention("Curitiba", "LOC")], [mention("Curitiba - Paraná", "LOC")]).correct
    assert not row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "ORG")]).correct


def test_a_document_the_curator_left_empty_is_correct_when_nothing_was_found() -> None:
    """
    An empty gold is an answer, not a gap.

    It is the only thing that turns "the model invented an entity" into a measured false positive
    instead of an invisible one — the same reason the typology set has a NENHUMA bucket.
    """
    assert row("a", [], []).correct
    assert not row("a", [], [mention("Curitiba", "LOC")]).correct


def test_agreement_counts_documents_and_not_mentions() -> None:
    rows = [
        row("a", [], []),
        row("b", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]),
        row("c", [mention("Paraná", "LOC")], []),
    ]

    assert agreement(rows) == pytest.approx(2 / 3)


def test_the_empty_rate_counts_the_documents_nothing_was_found_in() -> None:
    rows = [row("a", [], []), row("b", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")])]

    assert empty_rate(rows) == pytest.approx(0.5)


def test_the_type_distribution_reads_each_side() -> None:
    rows = [
        row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "ORG")]),
        row("b", [mention("David Carneiro", "PER")], []),
    ]

    assert type_distribution(rows, "gold") == Counter({"LOC": 1, "PER": 1})
    assert type_distribution(rows, "predicted") == Counter({"ORG": 1})


def test_one_predicted_type_is_a_collapse_with_zero_entropy() -> None:
    counts = Counter({"ORG": 12})

    assert entropy_bits(counts) == 0.0
    assert largest_share(counts) == ("ORG", 1.0)


def test_the_entropy_is_positive_when_the_engine_uses_two_types() -> None:
    counts = Counter({"ORG": 3, "LOC": 3})

    assert entropy_bits(counts) == pytest.approx(1.0)
    assert largest_share(counts)[1] == pytest.approx(0.5)


# =============================================================================
# The labelled set: its shape and its signature
# =============================================================================


def write_pairs(path: Path, pairs: list[dict], status: str = "aprovado por Teste em 2026-01-01") -> Path:
    # A row is "read" when it carries the curator's certainty or a note; the loader enforces it, so
    # the fixtures mark their rows reviewed unless a test is specifically about an untouched one.
    for pair in pairs:
        pair.setdefault("confidence", "alta")
    payload = {"status": status, "instructions_for_the_curator": [], "pairs": pairs}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_a_signed_set_loads_its_mentions(tmp_path: Path) -> None:
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [{"description_id": "a", "expected": [{"term": "Curitiba", "type": "LOC"}]}],
    )

    rows, payload = load_labelled(path, allow_draft=False)

    assert rows[0].truth.mentions == (mention("Curitiba", "LOC"),)
    assert rows[0].truth.is_empty is False
    assert payload["status"].startswith("aprovado")


def test_a_draft_set_is_refused_without_the_flag(tmp_path: Path) -> None:
    """The signature is what makes the number quotable, and pre-annotation makes it matter more."""
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [{"description_id": "a", "expected": None}],
        status="draft — nenhum curador revisou este conjunto ainda",
    )

    with pytest.raises(SystemExit, match="no curator signed"):
        load_labelled(path, allow_draft=False)

    rows, _payload = load_labelled(path, allow_draft=True)

    assert rows[0].truth.is_empty


def test_a_row_that_was_never_corrected_is_refused(tmp_path: Path) -> None:
    """
    The proposal writes ``expected`` on every row, so a missing one is a correction nobody made.

    This is the failure the ``proposed``/``expected`` split exists to make impossible: a row left as
    the model wrote it would score the model against itself.
    """
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [{"description_id": "a", "proposed": [{"term": "Curitiba", "type": "LOC"}], "confidence": None}],
    )

    with pytest.raises(SystemExit, match="has no 'expected' field"):
        load_labelled(path, allow_draft=False)


def test_a_row_with_no_review_marker_is_left_out_of_the_score(tmp_path: Path) -> None:
    """
    ``expected: null`` is both "nothing should be found" and, untouched, the proposal's placeholder.

    Only the curator's certainty or a note tells the two apart, so a row carrying neither leaves the
    score — otherwise a forgotten row would silently measure the model against its own answer, which
    is the anchoring failure the design exists to prevent. It is counted, not dropped in silence.
    """
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [
            {"description_id": "read", "expected": [], "note": "o modelo inventou tudo"},
            {"description_id": "unread", "expected": [], "confidence": None, "note": ""},
        ],
    )

    rows, _payload = load_labelled(path, allow_draft=False)
    scoreable, unread, needs_decision = scorable_rows(rows)

    assert [row.description_id for row in scoreable] == ["read"]
    assert unread == ["unread"]
    assert needs_decision == 0


def test_a_needs_decision_row_is_not_counted_as_unread(tmp_path: Path) -> None:
    """The two exclusions answer different questions and a reader has to be able to tell them apart."""
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [{"description_id": "policy", "expected": [], "needs_decision": True, "confidence": None, "note": ""}],
    )

    rows, _payload = load_labelled(path, allow_draft=False)
    scoreable, unread, needs_decision = scorable_rows(rows)

    assert scoreable == []
    assert unread == []
    assert needs_decision == 1


def test_a_row_with_a_note_and_no_confidence_counts_as_reviewed(tmp_path: Path) -> None:
    """Clearing everything the model proposed is a correction, and the note is what records it."""
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [{"description_id": "a", "expected": [], "confidence": None, "note": "o modelo inventou tudo"}],
    )

    rows, _payload = load_labelled(path, allow_draft=False)

    assert rows[0].truth.is_empty


def test_a_mention_without_a_term_is_refused(tmp_path: Path) -> None:
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [{"description_id": "a", "expected": [{"term": "  ", "type": "LOC"}]}],
    )

    with pytest.raises(SystemExit, match="mention with no 'term'"):
        load_labelled(path, allow_draft=False)


def test_a_mention_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    path = write_pairs(tmp_path / "ner_pairs.json", [{"description_id": "a", "expected": ["Curitiba"]}])

    with pytest.raises(SystemExit, match="expected an object"):
        load_labelled(path, allow_draft=False)


def test_a_mention_without_a_type_is_counted_under_the_type_less_bucket(tmp_path: Path) -> None:
    """A curator who knows the term is an entity and not which kind is telling the truth."""
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [{"description_id": "a", "expected": [{"term": "Curitiba"}]}],
    )

    rows, _payload = load_labelled(path, allow_draft=False)

    assert rows[0].truth.mentions == (mention("Curitiba", NO_TYPE),)


def test_a_confidence_outside_the_vocabulary_is_refused(tmp_path: Path) -> None:
    path = write_pairs(
        tmp_path / "ner_pairs.json",
        [{"description_id": "a", "expected": None, "confidence": "certeza"}],
    )

    with pytest.raises(SystemExit, match="has confidence"):
        load_labelled(path, allow_draft=False)


def test_a_null_expected_is_an_empty_gold_and_not_a_missing_one(tmp_path: Path) -> None:
    path = write_pairs(tmp_path / "ner_pairs.json", [{"description_id": "a", "expected": None}])

    rows, _payload = load_labelled(path, allow_draft=False)

    assert rows[0].truth.is_empty


# =============================================================================
# Configurations
# =============================================================================


def test_parse_config_fills_the_empty_fields_from_the_worker() -> None:
    config = parse_config("spacy_ner", ("original_title", "scope_content"))

    assert config.engine == "spacy_ner"
    assert config.preset is None
    assert config.columns == ("original_title", "scope_content")
    assert config.label == "spacy_ner:-:original_title,scope_content"


def test_parse_config_reads_the_preset_and_the_columns() -> None:
    config = parse_config("spacy_ner:gpu:original_title", ("scope_content",))

    assert config.preset == "gpu"
    assert config.columns == ("original_title",)


def test_parse_config_refuses_a_column_the_ai_text_does_not_have() -> None:
    with pytest.raises(SystemExit, match="columns the AI text does not have"):
        parse_config("spacy_ner:gpu:not_a_column", ("original_title",))


def test_parse_config_refuses_too_many_fields() -> None:
    with pytest.raises(SystemExit, match="expected engine"):
        parse_config("spacy_ner:gpu:original_title:extra:more", ("original_title",))


# =============================================================================
# The report
# =============================================================================


def test_the_report_carries_the_breakdown_next_to_the_score() -> None:
    """
    The counts are data in the JSON and not only prose in the table.

    #69 could describe "the token-boundary blocking is a measurable defect" and nothing more; the
    number has to survive into the file a decision is written from.
    """
    config = BenchConfig(engine="spacy_ner", preset="gpu", columns=("original_title",))
    rows = [
        row("a", [mention("Curitiba", "LOC")], [mention("Curitiba", "LOC")]),
        row("b", [mention("Paraná", "LOC")], [mention("Paraná - Sul", "LOC")]),
    ]

    report = report_for(
        config,
        rows,
        labelled=2,
        needs_decision=0,
        missing=0,
        out_of_scope=0,
        unread=0,
        seconds_per_document=0.0,
        min_positives=1,
        predictions="live",
    )

    assert report["breakdown"]["hits"] == 1
    assert report["breakdown"]["boundary"] == 1
    assert report["agreement"] == pytest.approx(0.5)
    assert report["distribution"]["gold"] == {"LOC": 2}
    assert report["distribution"]["predicted"] == {"LOC": 2}
    assert report["types"][0]["label"] == OVERALL


def test_the_report_names_the_producer_of_the_stored_mode() -> None:
    """A `stored` score has to say whose output it read, because it is not the requested config."""
    config = BenchConfig(engine="spacy_ner", preset="gpu", columns=("original_title",))
    report = report_for(
        config,
        [row("a", [], [])],
        labelled=1,
        needs_decision=0,
        missing=0,
        out_of_scope=0,
        unread=0,
        seconds_per_document=0.0,
        min_positives=1,
        predictions="stored",
        producers=Counter({"abc123": 1, "(sem carimbo)": 2}),
    )

    assert report["producers"] == {"abc123": 1, "(sem carimbo)": 2}


def test_the_report_carries_the_configuration_the_engine_would_receive() -> None:
    config = BenchConfig(engine="spacy_ner", preset="lemmatizer", columns=("original_title",))

    report = report_for(
        config,
        [],
        labelled=0,
        needs_decision=0,
        missing=0,
        out_of_scope=0,
        unread=0,
        seconds_per_document=0.0,
        min_positives=1,
        predictions="live",
    )

    assert report["engine_config"]["disable"] == ["ner", "parser"]
    assert report["producer_identity"]


# =============================================================================
# The bucket a row was drawn for
# =============================================================================


def test_a_row_is_labelled_by_the_quota_it_filled_and_not_by_its_first_type() -> None:
    """
    A photograph that names a place and a person belongs to two quotas, and the label says which.

    Measured on the real collection: labelling by the first stored type reported the PER and ORG
    quotas as empty while forty rows each had been drawn for them, because nearly every document
    with any entity at all also has a location.
    """
    assert (
        Candidate(
            description_id="a",
            title="",
            stored=(mention("Curitiba", "LOC"), mention("David Carneiro", "PER")),
            proposed_by="PER",
        ).proposed_by
        == "PER"
    )
