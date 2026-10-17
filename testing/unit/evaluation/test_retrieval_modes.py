"""
Unit tests for the mode bench's report (issue #38).

The bench itself needs a database, a model and a labelled set, so what is testable without any of
them is the part a reader depends on: that the strata read the two formulations the labelled set
actually carries, that the bench measures every mode the contract exposes, and that the table it
prints says how many queries each average came from.
"""

from __future__ import annotations

from typing import get_args

from scrinalia.domains.archive.schemas.query_schema import SearchMode
from testing.evaluation.retrieval_modes import MODES, STRATA, to_markdown


def test_the_strata_read_the_two_formulations_the_labelled_pair_carries() -> None:
    pair = {
        "query": "enchentes e alagamentos em Curitiba",
        "title_term": "enchente",
        "expected_document_ids": ["28780"],
    }
    assert {name: read(pair) for name, read in STRATA} == {
        "sentence": "enchentes e alagamentos em Curitiba",
        "term": "enchente",
    }


def test_the_bench_measures_every_mode_the_contract_exposes() -> None:
    """A new mode must fail here until the bench scores it, instead of going unmeasured."""
    assert set(MODES) == set(get_args(SearchMode))


def _report() -> dict:
    return {
        "k": 10,
        "depth": 50,
        "queries": 16,
        "modes": ["lexical", "semantic", "hybrid"],
        "strata": ["sentence"],
        "set_declares": "memoriacuritibana (3608 documentos)",
        "scores": {
            "sentence": {
                "lexical": {
                    "hit_rate@10": 0.438,
                    "recall@10": 0.2,
                    "mrr": 0.258,
                    "coverage": 0.5,
                    "queries": 16,
                    "seconds": 8.0,
                },
                "semantic": {
                    "hit_rate@10": 0.562,
                    "recall@10": 0.3,
                    "mrr": 0.293,
                    "coverage": 0.75,
                    "queries": 16,
                    "seconds": 16.0,
                },
                "hybrid": {
                    "hit_rate@10": 0.625,
                    "recall@10": 0.3,
                    "mrr": 0.297,
                    "coverage": 0.812,
                    "queries": 16,
                    "seconds": 24.0,
                },
            }
        },
        "per_query": {"sentence": []},
    }


def test_the_table_carries_one_row_per_mode_and_seconds_per_query() -> None:
    markdown = to_markdown(_report())
    assert "| lexical | 0.438 |" in markdown
    assert "| hybrid | 0.625 |" in markdown
    # 8.0 s over 16 queries is half a second each, not eight.
    assert "| 0.50 |" in markdown


def test_the_table_says_how_many_queries_each_average_came_from() -> None:
    """Sixteen queries cannot separate 0.562 from 0.625, and the report must say so by number."""
    markdown = to_markdown(_report())
    assert "16 labelled queries" in markdown
    assert "memoriacuritibana (3608 documentos)" in markdown
