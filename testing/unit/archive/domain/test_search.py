import pytest

from scrinalia.domains.archive.domain.search import (
    RRF_K,
    build_tsquery,
    reciprocal_rank_fusion,
    tokenize,
)


def test_tokenize_keeps_accents_and_digits() -> None:
    assert tokenize("Praça do Gaúcho 1954") == ["Praça", "do", "Gaúcho", "1954"]


def test_tokenize_drops_every_tsquery_operator() -> None:
    """Punctuation cannot reach ``to_tsquery``: only word characters survive."""
    assert tokenize("iptu:* & (batel | dengue) !'x'") == ["iptu", "batel", "dengue", "x"]
    assert tokenize("a-b_c") == ["a", "b", "c"]


def test_tokenize_returns_nothing_for_blank_or_punctuation_only() -> None:
    assert tokenize("   ") == []
    assert tokenize("&|!():*") == []


def test_build_tsquery_prefixes_only_the_last_token() -> None:
    assert build_tsquery(["matadouro"]) == "matadouro:*"
    assert build_tsquery(["praça", "gaúcho"]) == "praça & gaúcho:*"


def test_build_tsquery_is_none_without_tokens() -> None:
    """The caller must be able to skip the full-text clause entirely."""
    assert build_tsquery([]) is None


def test_reciprocal_rank_fusion_favours_the_document_both_rankings_found() -> None:
    """
    The pull that makes a fusion worth having: agreement at comparable positions wins.

    ``a`` leads the first ranking and ``b`` is second there, but ``b`` also leads the second one,
    so ``b`` comes first — a document no single ranking would have put first.
    """
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
    assert [description_id for description_id, _score in fused] == ["b", "a", "c"]


def test_reciprocal_rank_fusion_is_not_a_dominance_order() -> None:
    """
    Pinned so nobody describes the fusion as "the shared document always wins".

    A first place plus a third beats a second place twice by 8e-6, because the reciprocal is
    convex. It is a pull towards agreement, not a rule about it.
    """
    fused = dict(reciprocal_rank_fusion([["x", "p"], ["r", "p", "x"]]))
    assert fused["x"] > fused["p"]
    assert fused["x"] - fused["p"] < 1e-5


def test_reciprocal_rank_fusion_keeps_the_order_of_a_single_ranking() -> None:
    assert reciprocal_rank_fusion([["a", "b", "c"]]) == [
        ("a", 1.0 / (RRF_K + 1)),
        ("b", 1.0 / (RRF_K + 2)),
        ("c", 1.0 / (RRF_K + 3)),
    ]


def test_reciprocal_rank_fusion_is_an_empty_fusion_for_an_empty_ranking() -> None:
    """An arm with no candidate contributes nothing; it does not empty the result."""
    assert reciprocal_rank_fusion([[], ["a"]]) == [("a", 1.0 / (RRF_K + 1))]
    assert reciprocal_rank_fusion([]) == []


def test_reciprocal_rank_fusion_breaks_ties_by_description_id() -> None:
    """Equal scores must still order deterministically, or two runs disagree."""
    fused = reciprocal_rank_fusion([["b"], ["a"]])
    assert [description_id for description_id, _score in fused] == ["a", "b"]


def test_reciprocal_rank_fusion_counts_a_repeated_id_once() -> None:
    """A ranking is a ranking: a duplicated row does not buy a second vote."""
    assert reciprocal_rank_fusion([["a", "a", "b"]]) == [
        ("a", 1.0 / (RRF_K + 1)),
        ("b", 1.0 / (RRF_K + 3)),
    ]


def test_reciprocal_rank_fusion_rejects_a_negative_constant() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        reciprocal_rank_fusion([["a"]], k=-1)
