from core.schemas.silver_schema import SilverDescription


def test_silver_indexing_points_validator_substitui_pontos_e_virgulas() -> None:
    """Garante que o validador da Silver limpa as tags antes de enviar para a Gold."""

    dados_brutos = {
        "description_id": "doc-123",
        "title": "Documento Teste",
        "bronze_content_hash": "hash_123",
        "document_date": None,
        "raw_metadata": {"chave": "valor_teste"},
        "indexing_points": "Ofício; Curitiba; Indústria Têxtil",
    }

    dto = SilverDescription(**dados_brutos)

    assert dto.indexing_points == "Ofício, Curitiba, Indústria Têxtil"


def test_silver_indexing_points_aceita_nulo() -> None:
    """Garante que o validador não quebra se o documento não tiver tags."""

    dados_brutos = {
        "description_id": "doc-123",
        "title": "Documento Teste",
        "bronze_content_hash": "hash_123",
        "document_date": None,
        "raw_metadata": {},
        "indexing_points": None,
    }

    dto = SilverDescription(**dados_brutos)

    assert dto.indexing_points is None
