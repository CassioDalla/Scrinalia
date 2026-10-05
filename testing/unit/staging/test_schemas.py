from datetime import date

from memoria_curitibana.domains.staging.schemas import StagingDocumentDTO


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


def test_map_raw_to_staging_extracts_brazilian_date() -> None:
    """Guarantees that the Regex captures the DD/MM/YYYY pattern in the raw payload."""
    raw_data = {
        "description_id": "doc-2",
        "content_hash": "hash_xyz",
        "payload": {"title": "Ofício do Prefeito", "Data de Produção": "05/07/1929"},
    }

    dto = StagingDocumentDTO(**raw_data)

    assert dto.document_date == date(1929, 7, 5)


def test_map_raw_to_staging_saves_junk_in_raw_metadata() -> None:
    """Guarantees that unknown HTML keys are not lost."""
    raw_data = {
        "description_id": "doc-3",
        "content_hash": "hash_abc",
        "payload": {
            "title": "Documento Teste",
            "Código de Referência": "BR PRPMC",
            "Chave Bizarra Inesperada": "Valor Perdido",
        },
    }

    dto = StagingDocumentDTO(**raw_data)

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
        dto = StagingDocumentDTO(
            description_id="doc-1",
            content_hash="hash_1",
            payload={"title": "Série", "Código de Referência": "BR PRADAP SMU AL", spelling: "BR PRADAP SMU"},
        )
        assert dto.parent_reference_code == "BR PRADAP SMU"
        assert dto.reference_code == "BR PRADAP SMU AL"


def test_the_hierarchy_path_is_mapped_and_kept_out_of_the_unknown_bucket() -> None:
    dto = StagingDocumentDTO(
        description_id="doc-2",
        content_hash="hash_2",
        payload={
            "title": "Item",
            "Caminho Hierárquico": "BR PRADAP / BR PRADAP SMU / BR ITEM 1",
        },
    )
    assert dto.hierarchy_path == "BR PRADAP / BR PRADAP SMU / BR ITEM 1"
    assert "Caminho Hierárquico" not in dto.raw_metadata


def test_an_origin_that_declares_no_arrangement_is_still_valid() -> None:
    """The columns are optional by design: staying silent must not break a load."""
    dto = StagingDocumentDTO(
        description_id="doc-3", content_hash="hash_3", payload={"title": "Item", "Código de Referência": "BR X"}
    )
    assert dto.parent_reference_code is None
    assert dto.hierarchy_path is None
