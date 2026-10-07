from scrinalia.domains.archive.domain.search import build_tsquery, tokenize


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
