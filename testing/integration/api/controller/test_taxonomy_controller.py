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

from memoria_curitibana.asgi import create_app
from memoria_curitibana.domains.archive.exceptions import InvalidMergeError, TagNotFoundError
from memoria_curitibana.domains.archive.schemas.tag_schema import TagRelevanceIdf  # <-- Import the DTO
from memoria_curitibana.domains.archive.services.entity_service import EntityService
from memoria_curitibana.domains.archive.services.tag_service import TagService


# ==========================================
# HTTP CLIENT FIXTURE
# ==========================================
@pytest.fixture
def client() -> TestClient:  # type: ignore
    """Provides a test HTTP client for Litestar."""
    with TestClient(app=create_app()) as client:
        yield client  # type: ignore


# ==========================================
# 1. HAPPY PATH TESTS (STATUS 200 OK)
# ==========================================


def test_get_tag_relevance_returns_200(client: TestClient, mocker):
    """Guarantees that the GET route returns the correct structured data."""
    # We mock only the service response
    mock_service = mocker.patch.object(TagService, "get_tag_relevance_tfidf")

    mock_service.return_value = [TagRelevanceIdf(name="Curitiba", score_tfidf=0.99, frequency=1, weight_idf=1)]

    # The route in the Controller is defined as /tags/relevance/{method:str}
    response = client.get("/api/v1/taxonomy/tags/relevance/tfidf?limit=10")

    assert response.status_code == HTTP_200_OK

    # TagRelevanceResponse always uses the "payload" envelope.
    response_json = response.json()
    assert response_json["mode"] == "tfidf"
    assert len(response_json["payload"]) == 1
    assert response_json["payload"][0]["name"] == "Curitiba"
    mock_service.assert_called_once_with(10)


def test_merge_entities_returns_200(client: TestClient, mocker):
    """Guarantees that the POST works and returns the correct JSON envelope."""
    mock_service = mocker.patch.object(EntityService, "merge")

    # We simulate the service response DTO: EntityMergeResponse(documents_updated=5, entities_deleted=2)
    mock_service.return_value.documents_updated = 5
    mock_service.return_value.entities_deleted = 2

    payload = {"canonical_id": 1, "ids_to_merge": [2, 3]}

    response = client.post("/api/v1/taxonomy/entities/merge", json=payload)

    assert response.status_code == HTTP_201_CREATED
    assert response.json() == {"documents_updated": 5, "entities_deleted": 2}


# ==========================================
# 2. EXCEPTION HANDLER TESTS (STATUS 4XX)
# ==========================================


def test_merge_tags_triggers_400_when_business_rule_fails(client: TestClient, mocker):
    """
    Tests the domain_exception_handler.
    If the service raises InvalidMergeError, the API MUST return 400 Bad Request.
    """
    mock_service = mocker.patch.object(TagService, "merge")
    # We force the service to raise a domain error (e.g., tried to merge the tag with itself)
    mock_service.side_effect = InvalidMergeError("O ID canônico não pode estar na exclusão.")

    payload = {"canonical_id": 10, "ids_to_merge": [10]}
    response = client.post("/api/v1/taxonomy/tags/merge", json=payload)

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error_code"] == "InvalidMergeError"
    assert "canônico não pode estar" in response.json()["message"]


def test_route_triggers_404_when_entity_not_found(client: TestClient, mocker):
    """Tests whether the NotFound error is correctly mapped to HTTP 404."""
    mock_service = mocker.patch.object(TagService, "merge")
    mock_service.side_effect = TagNotFoundError("Tag não encontrada.")

    response = client.post("/api/v1/taxonomy/tags/merge", json={"canonical_id": 999, "ids_to_merge": [1]})

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "TagNotFoundError"


def test_route_triggers_409_on_database_conflict(client: TestClient, mocker):
    """
    Tests the integrity_error_handler.
    If the database screams, the API returns 409 Conflict.
    """
    # The handler saves the words before purging; we isolate the two operations.
    mocker.patch.object(TagService, "save_new_stopwords", return_value=0)
    mock_service = mocker.patch.object(TagService, "purge_stopwords")

    # We simulate a SQLAlchemy IntegrityError (e.g., constraint violation)
    mock_service.side_effect = IntegrityError("statement", "params", "orig")  # type: ignore

    response = client.post("/api/v1/taxonomy/tags/stopwords/purge", json={"words": ["a", "o"]})

    assert response.status_code == HTTP_409_CONFLICT
    assert response.json()["error_code"] == "IntegrityError"
    assert "Conflito estrutural" in response.json()["message"]
