"""
The origin registry: which origins this deployment can read, and how their vocabularies are checked.

The registry is small and the tests are about its silent failure modes: a missing origin must fail
fast instead of mapping every column as unknown, a typo in a map must be a test failure instead of a
column filed as unknown, and adding a second origin must not make the transform learn its labels.
"""

import pytest

from scrinalia.core.config import settings
from scrinalia.domains.ingestion.adapters.csv import CSV_SOURCE_SCHEMA
from scrinalia.domains.ingestion.adapters.manual import MANUAL_FIELDS, MANUAL_SOURCE_SCHEMA
from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA
from scrinalia.domains.ingestion.csv_import import CSV_FIELD_MAP, CSV_FIELDS, CSV_TITLE_LABEL
from scrinalia.domains.ingestion.exceptions import InvalidOriginConfigError, OriginNotFoundError
from scrinalia.domains.ingestion.origin_registry import ORIGINS
from scrinalia.domains.ingestion.ports import OriginAdapters
from scrinalia.domains.ingestion.schemas import ManualIngestionRequest
from scrinalia.domains.ingestion.sources import ADAPTERS, SOURCES, get_adapters, get_source_schema
from scrinalia.domains.staging.schemas import StagingDocumentDTO


def test_every_shipped_origin_is_registered() -> None:
    assert set(SOURCES) == set(ADAPTERS) == set(ORIGINS) == {"pmc", "manual", "csv"}


def test_each_origin_has_its_own_vocabulary() -> None:
    assert get_source_schema("pmc") is PMC_SOURCE_SCHEMA
    assert get_source_schema("manual") is MANUAL_SOURCE_SCHEMA
    assert get_source_schema("csv") is CSV_SOURCE_SCHEMA
    assert len({id(PMC_SOURCE_SCHEMA), id(MANUAL_SOURCE_SCHEMA), id(CSV_SOURCE_SCHEMA)}) == 3


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


def test_the_csv_vocabulary_is_the_import_catalogue() -> None:
    """
    The file's headers are the labels, and the title/date are consumed by the schema's own keys.

    Keeping the title out of ``field_map`` is load-bearing: the transform would append it to itself
    (``Ofício | Ofício``) instead of reading it once through ``title_key``.
    """
    assert CSV_SOURCE_SCHEMA.field_map is CSV_FIELD_MAP
    assert CSV_SOURCE_SCHEMA.title_key == CSV_TITLE_LABEL == "Título"
    assert CSV_SOURCE_SCHEMA.date_keys == ("Data de produção",)
    assert "Título" not in CSV_SOURCE_SCHEMA.field_map
    assert "Data de produção" not in CSV_SOURCE_SCHEMA.field_map
    assert CSV_SOURCE_SCHEMA.field_map["Código de referência"] == "reference_code"


def test_the_csv_vocabulary_is_the_manual_contract() -> None:
    """
    The CSV accepts the manual contract's field set, and #192 expands both together.

    The set equality is the gate: a field added to ``ManualIngestionRequest`` without a label here
    (or a label pointing at an attribute the model does not have) fails before the route can file
    the column as unknown. ``description_id`` is the row's identity, outside the payload.
    """
    attributes = {field.attribute for field in CSV_FIELDS}
    manual = set(ManualIngestionRequest.model_fields) - {"description_id"}
    assert attributes == manual
    assert len({field.label for field in CSV_FIELDS}) == len(CSV_FIELDS)


def test_every_manual_field_reaches_the_payload() -> None:
    """
    The tuple the service iterates and the model the route validates name the same fields.

    ``_manual_payload`` walks ``MANUAL_FIELDS`` and reads each attribute off the request, so a field
    added to the model and forgotten there is dropped **in silence** — the route answers 201, the
    staging record is written, and the value never leaves the request. The three the service handles
    itself (the identity, the title and the date) are the exception, and they are named here.
    """
    described = set(MANUAL_FIELDS) | {"title", "document_date"}
    manual = set(ManualIngestionRequest.model_fields) - {"description_id"}

    assert described == manual, f"o modelo tem {sorted(manual - described)}; a lista tem {sorted(described - manual)}"


def test_the_manual_date_is_read_by_the_language_grammar() -> None:
    """
    One grammar for both entrances: what the CSV accepts, the form accepts.

    ``Década de 1980`` is a legitimate date — the parser turns it into January 1st of the decade and
    the archive keeps the spelling — while "banana" is a sentence the archivist can act on, not a
    silent ``None`` in staging.
    """
    from pydantic import ValidationError

    fuzzy = ManualIngestionRequest(title="Ofício", document_date="  Década de 1980  ")
    assert fuzzy.document_date == "Década de 1980"

    placeholder = ManualIngestionRequest(title="Ofício", document_date="00/00/0000")
    assert placeholder.document_date is None

    with pytest.raises(ValidationError):
        ManualIngestionRequest(title="Ofício", document_date="banana")


def test_the_csv_field_caps_are_the_manual_ones() -> None:
    """A cap looser than the contract's would make the front accept a row the route refuses."""
    from annotated_types import MaxLen

    for field in CSV_FIELDS:
        model_field = ManualIngestionRequest.model_fields.get(field.attribute)
        if model_field is None:
            continue
        caps = [cap.max_length for cap in model_field.metadata if isinstance(cap, MaxLen)]
        if caps:
            assert field.max_length == caps[0], f"{field.label} tem limite {field.max_length} != {caps[0]}"


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


def test_only_the_sources_are_configurable() -> None:
    """The page's sources are the configurable definitions; the entries are never offered (#206).

    The manual and CSV entries are input paths with rows for provenance, not origins to add. A new
    source marked configurable has to show up here, so making an entry addable is a deliberate line
    in a diff rather than a default nobody reviewed.
    """
    configurable = {summary.code for summary in ORIGINS.values() if summary.configurable}
    assert configurable == {"pmc"}, f"a nova origem configurável precisa entrar aqui: {configurable}"


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
    assert set(ADAPTERS) == set(SOURCES) == {"pmc", "manual", "csv"}


def test_a_form_based_origin_declares_no_port() -> None:
    """The CSV (like the manual origin) writes its rows itself; asking for a phase names it."""
    adapters = get_adapters("csv")
    assert adapters.discovery is None and adapters.detail is None
    with pytest.raises(ValueError, match="no discovery phase"):
        adapters.require_discovery()


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
