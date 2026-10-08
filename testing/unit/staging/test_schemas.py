from datetime import date

import pytest

from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA
from scrinalia.domains.staging.schemas import SOURCE_SCHEMA_CONTEXT_KEY, StagingDocumentDTO


def _from_payload(payload: dict, **extra) -> StagingDocumentDTO:
    """Builds the DTO the way the pipeline does: through the origin's schema."""
    return StagingDocumentDTO.model_validate(
        {"description_id": "doc-1", "content_hash": "hash-1", "payload": payload, **extra},
        context={SOURCE_SCHEMA_CONTEXT_KEY: PMC_SOURCE_SCHEMA},
    )


def test_silver_indexing_points_validator_replaces_semicolons() -> None:
    """Guarantees that the Silver validator cleans the tags before sending them to Gold."""

    raw_data = {
        "description_id": "doc-123",
        "title": "Documento Teste",
        "raw_content_hash": "hash_123",
        "document_date": None,
        "raw_metadata": {"chave": "valor_teste"},
        "indexing_points": "Ofício; Curitiba; Indústria Têxtil",
    }

    dto = StagingDocumentDTO(**raw_data)

    assert dto.indexing_points == "Ofício, Curitiba, Indústria Têxtil"


def test_silver_indexing_points_accepts_null() -> None:
    """Guarantees that the validator does not break if the document has no tags."""

    raw_data = {
        "description_id": "doc-123",
        "title": "Documento Teste",
        "raw_content_hash": "hash_123",
        "document_date": None,
        "raw_metadata": {},
        "indexing_points": None,
    }

    dto = StagingDocumentDTO(**raw_data)

    assert dto.indexing_points is None


def test_clean_text_fields_converts_false_nulls_to_none() -> None:
    """Guarantees that the validator cleans useless legacy strings."""
    data = {
        "description_id": "doc-1",
        "raw_content_hash": "hash",
        "title": "Titulo",
        "producers": "Não Informado",
        "access_conditions": "-",
        "scope_content": "n/a",
        "rules_conventions": "Nenhum",
    }

    dto = StagingDocumentDTO(**data)  # type: ignore

    assert dto.producers is None
    assert dto.access_conditions is None
    assert dto.scope_content is None
    assert dto.rules_conventions is None


def test_the_false_nulls_come_from_the_language_profile() -> None:
    """
    The spellings are the profile's, not a list inside the DTO.

    ``ilegível`` and ``sem identificação`` used to be false nulls only for the subject guard, so a
    producer named ``ilegível`` survived as text while a tag named ``ilegível`` was refused. One
    definition means both answers agree.
    """
    dto = StagingDocumentDTO(
        description_id="doc-1",
        raw_content_hash="hash",
        title="Titulo",
        producers="ilegível",
        provenance="sem identificação",
        accruals="não possui",
    )

    assert dto.producers is None
    assert dto.provenance is None
    assert dto.accruals is None


def test_map_raw_to_staging_extracts_brazilian_date() -> None:
    """Guarantees that the Regex captures the DD/MM/YYYY pattern in the raw payload."""
    dto = _from_payload({"title": "Ofício do Prefeito", "Data de Produção": "05/07/1929"})

    assert dto.document_date == date(1929, 7, 5)


def test_the_date_also_arrives_under_the_short_spelling() -> None:
    """The origin names the date twice; the schema lists both, most specific first."""
    assert _from_payload({"title": "X", "Data": "1954"}).document_date == date(1954, 1, 1)


def test_map_raw_to_staging_saves_junk_in_raw_metadata() -> None:
    """Guarantees that unknown HTML keys are not lost."""
    dto = _from_payload(
        {
            "title": "Documento Teste",
            "Código de Referência": "BR PRPMC",
            "Chave Bizarra Inesperada": "Valor Perdido",
        }
    )

    assert dto.reference_code == "BR PRPMC"
    assert "Chave Bizarra Inesperada" in dto.raw_metadata
    assert dto.raw_metadata["Chave Bizarra Inesperada"] == "Valor Perdido"


def test_the_declared_superior_unit_is_mapped_from_every_spelling() -> None:
    """
    H6's half of the contract: the origin names the superior unit in Portuguese, and any of the
    spellings an origin may use has to land on the same field.
    """
    for spelling in (
        "Unidade de Descrição Superior",
        "Unidade de Descrição Pai",
        "Nível Superior",
        "Código da Unidade Superior",
    ):
        dto = _from_payload({"title": "Série", "Código de Referência": "BR PRADAP SMU AL", spelling: "BR PRADAP SMU"})
        assert dto.parent_reference_code == "BR PRADAP SMU"
        assert dto.reference_code == "BR PRADAP SMU AL"


def test_the_hierarchy_path_is_mapped_and_kept_out_of_the_unknown_bucket() -> None:
    dto = _from_payload(
        {
            "title": "Item",
            "Caminho Hierárquico": "BR PRADAP / BR PRADAP SMU / BR ITEM 1",
        }
    )
    assert dto.hierarchy_path == "BR PRADAP / BR PRADAP SMU / BR ITEM 1"
    assert "Caminho Hierárquico" not in dto.raw_metadata


def test_an_origin_that_declares_no_arrangement_is_still_valid() -> None:
    """The columns are optional by design: staying silent must not break a load."""
    dto = _from_payload({"title": "Item", "Código de Referência": "BR X"})
    assert dto.parent_reference_code is None
    assert dto.hierarchy_path is None


def test_the_adapters_own_keys_do_not_leak_into_the_unknown_bucket() -> None:
    """The title and the page URL are the record's identity, not unknown junk."""
    dto = _from_payload({"title": "Item", "_url_origem": "https://exemplo/1", "attch_down_link": "https://ex.pdf"})

    assert dto.original_url == "https://exemplo/1"
    assert dto.attachment_link == "https://ex.pdf"
    assert dto.raw_metadata == {}


# ==========================================
# THE ORIGIN'S SCHEMA IS REQUIRED
# ==========================================


def test_a_placeholder_title_becomes_the_language_placeholder() -> None:
    """
    A record whose only defect is a placeholder title must load, not be dropped.

    Measured before this rule existed: a payload with ``"não informado"`` as the title failed
    validation, because ``title`` is required and the false-null cleaning turned it into ``None``.
    The whole document was lost to a placeholder — the staging layer quietly discarding a record the
    origin had delivered.
    """
    for placeholder in ("não informado", "SEM TÍTULO", "-", "nenhum"):
        dto = _from_payload({"title": placeholder})
        assert dto.title == "SEM TÍTULO", f"{placeholder!r} é um título ausente, não um título"


def test_a_real_title_is_kept() -> None:
    assert _from_payload({"title": "  Ofício   do Prefeito  "}).title == "Ofício do Prefeito"


def test_the_transform_refuses_to_run_without_the_origin_schema() -> None:
    """
    Without a schema the transform cannot know which label fills which column.

    Refusing is the point: mapping nothing would file every column as unknown and the archivist
    would see empty records instead of an error, which is the harder failure to diagnose.
    """
    with pytest.raises(Exception, match="SourceSchema"):
        StagingDocumentDTO.model_validate({"description_id": "doc-1", "content_hash": "h", "payload": {"title": "X"}})
