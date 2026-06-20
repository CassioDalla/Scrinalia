from datetime import date

from domains.staging.schemas import StagingDocumentDTO


def test_silver_indexing_points_validator_substitui_pontos_e_virgulas() -> None:
    """Garante que o validador da Silver limpa as tags antes de enviar para a Gold."""

    dados_brutos = {
        "description_id": "doc-123",
        "title": "Documento Teste",
        "raw_content_hash": "hash_123",
        "document_date": None,
        "raw_metadata": {"chave": "valor_teste"},
        "indexing_points": "Ofício; Curitiba; Indústria Têxtil",
    }

    dto = StagingDocumentDTO(**dados_brutos)

    assert dto.indexing_points == "Ofício, Curitiba, Indústria Têxtil"


def test_silver_indexing_points_aceita_nulo() -> None:
    """Garante que o validador não quebra se o documento não tiver tags."""

    dados_brutos = {
        "description_id": "doc-123",
        "title": "Documento Teste",
        "raw_content_hash": "hash_123",
        "document_date": None,
        "raw_metadata": {},
        "indexing_points": None,
    }

    dto = StagingDocumentDTO(**dados_brutos)

    assert dto.indexing_points is None


def test_clean_text_fields_converte_falsos_nulos_para_none() -> None:
    """Garante que o validador limpa strings inúteis do legado."""
    dados = {
        "description_id": "doc-1",
        "raw_content_hash": "hash",
        "title": "Titulo",
        "producers": "Não Informado",
        "access_conditions": "-",
        "scope_content": "n/a",
        "rules_conventions": "Nenhum",
    }

    dto = StagingDocumentDTO(**dados)  # type: ignore

    assert dto.producers is None
    assert dto.access_conditions is None
    assert dto.scope_content is None
    assert dto.rules_conventions is None


def test_map_raw_to_staging_extrai_data_brasileira() -> None:
    """Garante que a Regex captura o padrão DD/MM/YYYY no payload bruto."""
    dados_brutos = {
        "description_id": "doc-2",
        "content_hash": "hash_xyz",
        "payload": {"title": "Ofício do Prefeito", "Data de Produção": "05/07/1929"},
    }

    dto = StagingDocumentDTO(**dados_brutos)

    assert dto.document_date == date(1929, 7, 5)


def test_map_raw_to_staging_salva_lixo_no_raw_metadata() -> None:
    """Garante que chaves desconhecidas do HTML não são perdidas."""
    dados_brutos = {
        "description_id": "doc-3",
        "content_hash": "hash_abc",
        "payload": {
            "title": "Documento Teste",
            "Código de Referência": "BR PRPMC",
            "Chave Bizarra Inesperada": "Valor Perdido",
        },
    }

    dto = StagingDocumentDTO(**dados_brutos)

    assert dto.reference_code == "BR PRPMC"
    assert "Chave Bizarra Inesperada" in dto.raw_metadata
    assert dto.raw_metadata["Chave Bizarra Inesperada"] == "Valor Perdido"
