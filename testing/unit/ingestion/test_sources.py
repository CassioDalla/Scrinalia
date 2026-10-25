"""
The origin registry: which origins this deployment can read, and how their vocabularies are checked.

The registry is small and the tests are about its silent failure modes: a missing origin must fail
fast instead of mapping every column as unknown, a typo in a map must be a test failure instead of a
column filed as unknown, and adding a second origin must not make the transform learn its labels.
"""

import pytest

from scrinalia.core.config import settings
from scrinalia.domains.ingestion.adapters.manual import MANUAL_SOURCE_SCHEMA
from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA
from scrinalia.domains.ingestion.exceptions import InvalidOriginConfigError, OriginNotFoundError
from scrinalia.domains.ingestion.origin_registry import ORIGINS
from scrinalia.domains.ingestion.ports import OriginAdapters
from scrinalia.domains.ingestion.sources import ADAPTERS, SOURCES, get_adapters, get_source_schema
from scrinalia.domains.staging.schemas import StagingDocumentDTO


def test_every_shipped_origin_is_registered() -> None:
    assert set(SOURCES) == set(ADAPTERS) == set(ORIGINS) == {"pmc", "manual"}


def test_each_origin_has_its_own_vocabulary() -> None:
    assert get_source_schema("pmc") is PMC_SOURCE_SCHEMA
    assert get_source_schema("manual") is MANUAL_SOURCE_SCHEMA
    assert PMC_SOURCE_SCHEMA is not MANUAL_SOURCE_SCHEMA


def test_a_missing_origin_fails_fast() -> None:
    """
    There is no default, on purpose.

    A default would make a record whose origin was never named read the reference site's labels —
    the "the default is Curitiba" defect ADR 0008 removed from the collection vocabulary, repeated
    one layer down.
    """
    with pytest.raises(OriginNotFoundError, match="Informe a origem"):
        get_source_schema(None)


def test_an_unknown_origin_names_the_known_ones() -> None:
    with pytest.raises(OriginNotFoundError, match="não existe"):
        get_source_schema("inexistente")


@pytest.mark.parametrize("code", sorted(SOURCES))
def test_every_mapped_attribute_is_a_real_column(code: str) -> None:
    """
    A typo on the right-hand side of the map would file that column as unknown without failing.

    The map's *values* are the staging model's attributes, so the model itself is the check. It runs
    for **every** origin, which is what keeps a second origin's map honest.
    """
    columns = set(StagingDocumentDTO.model_fields)
    unknown = {attribute for attribute in SOURCES[code].field_map.values() if attribute not in columns}
    assert unknown == set(), f"{code} aponta para colunas que não existem: {sorted(unknown)}"


def test_the_origin_labels_are_not_translated() -> None:
    """
    The keys are the site's own labels, scraped from the page.

    Translating one would make it stop matching the payload, and the column would quietly empty.
    This pins a couple of the measured spellings so a well-meaning rename is caught.
    """
    assert "Código de Referência" in PMC_SOURCE_SCHEMA.field_map
    assert "Âmbito e Conteúdo" in PMC_SOURCE_SCHEMA.field_map
    assert PMC_SOURCE_SCHEMA.date_keys == ("Data de Produção", "Data")


def test_the_manual_vocabulary_is_the_form_keys() -> None:
    """The manual source's labels are the form's; the transform still reads them from the schema."""
    assert "scope_content" in MANUAL_SOURCE_SCHEMA.field_map
    assert MANUAL_SOURCE_SCHEMA.title_key == "title"
    assert MANUAL_SOURCE_SCHEMA.date_keys == ("document_date",)


def test_every_origin_config_field_names_a_model_field() -> None:
    """
    The screen's fields are metadata about the origin's own model, not a second validation.

    A URL added to the model and forgotten in the metadata would be unreachable from the screen; a
    metadata field the model does not have would be a form control that the API refuses. The pair is
    checked here so neither can drift alone.
    """
    for summary in ORIGINS.values():
        described = {field.name for field in summary.config_fields}
        model_fields = set(summary.config_model.model_fields)
        assert described == model_fields, f"{summary.code}: tela {described} != modelo {model_fields}"


# ==========================================
# THE ORIGIN'S PORTS
# ==========================================


def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PUBLIC_SCRAPE_URL", "https://exemplo.test/acervo")
    monkeypatch.setattr(settings, "PUBLIC_SCRAPE_DETAIL_URL", "https://exemplo.test/acervo/detalhe")


def test_the_reference_origin_registers_both_phases(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch)

    adapters = get_adapters("pmc")

    # One adapter object, because this site implements both ports.
    assert adapters.require_discovery() is adapters.require_detail()


def test_the_adapters_registry_is_the_source_registry() -> None:
    assert set(ADAPTERS) == set(SOURCES) == {"pmc", "manual"}


def test_a_missing_scrape_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The fail-fast moved with the adapter, and it still fires before an adapter exists.

    The reference origin accepts the environment as a fallback for its URLs (that is what keeps an
    existing ``.env`` working); with neither the row nor the environment saying where it is, the
    refusal is a sentence and not a request to ``https://None``.
    """
    monkeypatch.setattr(settings, "PUBLIC_SCRAPE_URL", None)
    monkeypatch.setattr(settings, "PUBLIC_SCRAPE_DETAIL_URL", None)
    with pytest.raises(InvalidOriginConfigError, match="base_url"):
        get_adapters("pmc", config={})


def test_the_row_config_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The origin row is the operator's; the environment is only the fallback for the reference."""
    _configured(monkeypatch)
    adapters = get_adapters(
        "pmc",
        config={
            "base_url": "https://outro.test/lista",
            "detail_url": "https://outro.test/detalhe",
            "delay_requests": 0,
        },
    )
    adapter = adapters.require_detail()
    assert adapter.detail_url == "https://outro.test/detalhe"  # type: ignore[attr-defined]


def test_a_phase_an_origin_does_not_declare_is_a_sentence() -> None:
    """
    An origin is not necessarily a paginated site.

    The manual origin has no discovery and no detail page: its input is the form. Asking for the
    phase it does not implement must name it instead of raising ``AttributeError`` deep inside the
    job.
    """
    listing_only = OriginAdapters(code="manual")

    with pytest.raises(ValueError, match="no discovery phase"):
        listing_only.require_discovery()
    with pytest.raises(ValueError, match="no detail phase"):
        listing_only.require_detail()
