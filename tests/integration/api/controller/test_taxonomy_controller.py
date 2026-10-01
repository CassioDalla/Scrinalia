import pytest
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)
from litestar.testing import TestClient
from sqlalchemy.exc import IntegrityError

from domains.archive.exceptions import InvalidMergeError, TagNotFoundError
from domains.archive.schemas.tag_schema import TagRelevanceIdf  # <-- Importe o DTO
from domains.archive.services.entity_service import EntityService
from domains.archive.services.tag_service import TagService
from main import app


# ==========================================
# FIXTURE DO CLIENTE HTTP
# ==========================================
@pytest.fixture
def client() -> TestClient:  # type: ignore
    """Disponibiliza um cliente HTTP de testes para o Litestar."""
    with TestClient(app=app) as client:
        yield client  # type: ignore


# ==========================================
# 1. TESTES DE CAMINHO FELIZ (STATUS 200 OK)
# ==========================================


def test_get_tag_relevance_retorna_200(client: TestClient, mocker):
    """Garante que a rota GET devolve os dados estruturados corretos."""
    # Mockamos apenas a resposta do serviço
    mock_service = mocker.patch.object(TagService, "get_tag_relevance_tfidf")

    mock_service.return_value = [TagRelevanceIdf(name="Curitiba", score_tfidf=0.99, frequency=1, weight_idf=1)]

    # A rota no Controller está definida como /tags/relevance/{method:str}
    response = client.get("/api/v1/taxonomy/tags/relevance/tfidf?limit=10")

    assert response.status_code == HTTP_200_OK

    # Detetamos dinamicamente se você nomeou o envelope como "data" ou "payload"
    resposta_json = response.json()
    chave_envelope = "data" if "data" in resposta_json else "payload"

    assert len(resposta_json[chave_envelope]) == 1
    assert resposta_json[chave_envelope][0]["name"] == "Curitiba"
    mock_service.assert_called_once_with(10)


def test_merge_entities_retorna_200(client: TestClient, mocker):
    """Garante que o POST funciona e retorna o envelope JSON correto."""
    mock_service = mocker.patch.object(EntityService, "merge")

    # Simulamos o DTO de resposta do serviço: EntityMergeResponse(documents_updated=5, entities_deleted=2)
    mock_service.return_value.documents_updated = 5
    mock_service.return_value.entities_deleted = 2

    payload = {"canonical_id": 1, "ids_to_merge": [2, 3]}

    response = client.post("/api/v1/taxonomy/entities/merge", json=payload)

    assert response.status_code == HTTP_201_CREATED
    assert response.json() == {"documents_updated": 5, "entities_deleted": 2}


# ==========================================
# 2. TESTES DOS EXCEPTION HANDLERS (STATUS 4XX)
# ==========================================


def test_merge_tags_dispara_400_quando_regra_negocio_falha(client: TestClient, mocker):
    """
    Testa o domain_exception_handler.
    Se o serviço lançar InvalidMergeError, a API DEVE retornar 400 Bad Request.
    """
    mock_service = mocker.patch.object(TagService, "merge")
    # Forçamos o serviço a lançar um erro de domínio (ex: tentou fundir a tag com ela mesma)
    mock_service.side_effect = InvalidMergeError("O ID canônico não pode estar na exclusão.")

    payload = {"canonical_id": 10, "ids_to_merge": [10]}
    response = client.post("/api/v1/taxonomy/tags/merge", json=payload)

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error_code"] == "InvalidMergeError"
    assert "canônico não pode estar" in response.json()["message"]


def test_rota_dispara_404_quando_entidade_nao_encontrada(client: TestClient, mocker):
    """Testa se o erro de NotFound é corretamente mapeado para HTTP 404."""
    mock_service = mocker.patch.object(TagService, "merge")
    mock_service.side_effect = TagNotFoundError("Tag não encontrada.")

    response = client.post("/api/v1/taxonomy/tags/merge", json={"canonical_id": 999, "ids_to_merge": [1]})

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "TagNotFoundError"


def test_rota_dispara_409_quando_ha_conflito_banco(client: TestClient, mocker):
    """
    Testa o integrity_error_handler.
    Se o banco de dados berrar, a API devolve 409 Conflict.
    """
    # O handler grava as palavras antes de expurgar; isolamos as duas operações.
    mocker.patch.object(TagService, "save_new_stopwords", return_value=0)
    mock_service = mocker.patch.object(TagService, "purge_stopwords")

    # Simulamos um IntegrityError do SQLAlchemy (ex: violação de constraint)
    mock_service.side_effect = IntegrityError("statement", "params", "orig")  # type: ignore

    response = client.post("/api/v1/taxonomy/tags/stopwords/purge", json={"words": ["a", "o"]})

    assert response.status_code == HTTP_409_CONFLICT
    assert response.json()["error_code"] == "IntegrityError"
    assert "Conflito estrutural" in response.json()["message"]
