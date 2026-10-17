"""
Unit tests for the retrieval benches' shared ranking arithmetic (issue #38).

The arithmetic is the part that can be wrong in silence: it runs without a model and without a
database, so nothing in a manual run would notice Hit@10 counting a document at position 11, or the
reciprocal rank being read from the wrong cut. Two benches report these numbers, which is why they
are defined once and pinned here.
"""

from __future__ import annotations

from testing.evaluation.ranking_metrics import RankingScore, query_metrics


def test_hit_counts_a_document_inside_the_cut_off() -> None:
    measured = query_metrics({"7"}, ["1", "2", "7", "9"], k=3)
    assert measured.hit == 1.0
    assert measured.reciprocal_rank == 1 / 3
    assert measured.covered == 1.0


def test_a_document_just_past_the_cut_off_is_covered_but_not_a_hit() -> None:
    """The two questions are different: ranked too low, or not reached at all."""
    measured = query_metrics({"7"}, ["1", "2", "3", "7"], k=3)
    assert measured.hit == 0.0
    assert measured.covered == 1.0
    assert measured.reciprocal_rank == 1 / 4


def test_a_document_outside_the_ranking_scores_zero_everywhere() -> None:
    measured = query_metrics({"7"}, ["1", "2", "3"], k=3)
    assert (measured.hit, measured.recall, measured.reciprocal_rank, measured.covered) == (0.0, 0.0, 0.0, 0.0)


def test_recall_is_the_fraction_of_the_expected_set_inside_the_cut_off() -> None:
    measured = query_metrics({"1", "2", "3", "4"}, ["1", "2", "9"], k=3)
    assert measured.recall == 0.5


def test_the_reciprocal_rank_reads_the_first_expected_document() -> None:
    measured = query_metrics({"2", "3"}, ["1", "3", "2"], k=3)
    assert measured.reciprocal_rank == 1 / 2


def test_an_empty_expected_set_scores_zero_instead_of_dividing_by_it() -> None:
    measured = query_metrics(set(), ["1", "2"], k=2)
    assert (measured.hit, measured.recall, measured.reciprocal_rank, measured.covered) == (0.0, 0.0, 0.0, 0.0)


def test_the_accumulator_averages_over_the_queries_that_were_asked() -> None:
    """A query the method answers nothing for is a zero, not a shorter list that flatters it."""
    score = RankingScore()
    score.add({"1"}, ["1", "2"], k=2)
    score.add({"5"}, ["1", "2"], k=2)
    score.seconds = 4.0

    summary = score.summary(k=2)
    assert summary["hit_rate@2"] == 0.5
    # The first query found its expected id at position 1 and the second found nothing at all.
    assert summary["mrr"] == 0.5
    assert summary["coverage"] == 0.5
    assert summary["queries"] == 2.0
    assert summary["seconds"] == 4.0
