from memoria_curitibana.domains.archive.domain.normalization import (
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
