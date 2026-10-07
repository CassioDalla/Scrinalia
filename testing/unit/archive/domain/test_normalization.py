from scrinalia.domains.archive.domain.normalization import (
    is_blank,
    normalize_entity,
    normalize_stopword,
    normalize_synonym,
    normalize_tag,
)


def test_normalize_reduces_case_and_whitespace() -> None:
    assert normalize_tag("  Urbanismo ") == "urbanismo"
    assert normalize_entity("  Curitiba ") == "curitiba"
    assert normalize_synonym("  PMC  ") == "pmc"
    assert normalize_stopword("  Lixo ") == "lixo"


def test_normalize_is_idempotent() -> None:
    once = normalize_entity("Prefeitura de Curitiba")
    assert normalize_entity(once) == once


def test_is_blank() -> None:
    assert is_blank("") is True
    assert is_blank("   ") is True
    assert is_blank(None) is True  # type: ignore[arg-type]
    assert is_blank("x") is False


# ==========================================
# SINGULAR CANDIDATES (merge suggestions)
# ==========================================


def test_singular_candidates_cover_the_regular_endings() -> None:
    from scrinalia.domains.archive.domain.normalization import singular_candidates

    assert "livro" in singular_candidates("livros")
    assert "cidade" in singular_candidates("cidades")
    assert "caminhão" in singular_candidates("caminhões")
    assert "jornal" in singular_candidates("jornais")
    assert "papel" in singular_candidates("papéis")
    assert "jardim" in singular_candidates("jardins")
    assert "funil" in singular_candidates("funis")


def test_singular_candidates_are_hypotheses_validated_by_the_catalog() -> None:
    """
    ``ônibus`` has no singular and the rule proposes nothing that is the word itself: a
    candidate only becomes a merge suggestion when it already exists as a tag, so an
    irregular word is simply never matched.
    """
    from scrinalia.domains.archive.domain.normalization import singular_candidates

    assert "ônibus" not in singular_candidates("ônibus")
    assert all(candidate != "ônibus" for candidate in singular_candidates("ônibus"))


def test_singular_candidates_of_a_word_without_s_is_empty() -> None:
    from scrinalia.domains.archive.domain.normalization import singular_candidates

    assert singular_candidates("livro") == []
