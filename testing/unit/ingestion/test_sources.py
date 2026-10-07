"""
The origin registry: which site's vocabulary this deployment reads.

The registry is small and the tests are about its two failure modes, because both are silent
otherwise: a missing selection would map every column as unknown (empty records instead of an
error), and a typo in the map would file one column as unknown while the rest looked fine.
"""

import pytest

from scrinalia.core.config import settings
from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA
from scrinalia.domains.ingestion.sources import SOURCES, get_source_schema
from scrinalia.domains.staging.schemas import StagingDocumentDTO


@pytest.fixture(autouse=True)
def _clear_the_resolver_cache():
    """The resolver is ``lru_cache``d like ``get_settings``; a test must not inherit its answer."""
    get_source_schema.cache_clear()
    yield
    get_source_schema.cache_clear()


def test_the_reference_origin_is_registered() -> None:
    assert SOURCES == {"pmc": PMC_SOURCE_SCHEMA}


def test_an_explicit_code_wins() -> None:
    assert get_source_schema("pmc") is PMC_SOURCE_SCHEMA


def test_the_environment_selects_it_when_no_code_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ACERVO_SOURCE", "pmc")
    assert get_source_schema() is PMC_SOURCE_SCHEMA


def test_an_undeclared_origin_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    There is no fallback, on purpose.

    A default would make an installation that never declared its origin read the reference site's
    labels — the "the default is Curitiba" defect ADR 0008 removed from the collection vocabulary,
    repeated in a different place.
    """
    monkeypatch.setattr(settings, "ACERVO_SOURCE", None)
    with pytest.raises(ValueError, match="ACERVO_SOURCE"):
        get_source_schema()


def test_an_unknown_origin_names_the_known_ones() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        get_source_schema("inexistente")


def test_every_mapped_attribute_is_a_real_column() -> None:
    """
    A typo on the right-hand side of the map would file that column as unknown without failing.

    The map's *values* are the staging model's attributes, so the model itself is the check: this
    fails when a label is pointed at a column that does not exist.
    """
    columns = set(StagingDocumentDTO.model_fields)
    unknown = {attribute for attribute in PMC_SOURCE_SCHEMA.field_map.values() if attribute not in columns}
    assert unknown == set(), f"o mapa aponta para colunas que não existem: {sorted(unknown)}"


def test_the_origin_labels_are_not_translated() -> None:
    """
    The keys are the site's own labels, scraped from the page.

    Translating one would make it stop matching the payload, and the column would quietly empty.
    This pins a couple of the measured spellings so a well-meaning rename is caught.
    """
    assert "Código de Referência" in PMC_SOURCE_SCHEMA.field_map
    assert "Âmbito e Conteúdo" in PMC_SOURCE_SCHEMA.field_map
    assert PMC_SOURCE_SCHEMA.date_keys == ("Data de Produção", "Data")
