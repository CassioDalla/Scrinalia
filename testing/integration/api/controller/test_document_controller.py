"""HTTP contract of the documents controller.

The service is mocked on purpose: these tests pin the HTTP surface (status codes,
envelopes, parameter wiring), while the behaviour behind it is covered by the
service and repository suites.
"""

from datetime import date

import pytest
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND
from litestar.testing import TestClient

from memoria_curitibana.asgi import create_app
from memoria_curitibana.domains.archive.exceptions import DocumentNotFoundError
from memoria_curitibana.domains.archive.models import ArchiveReviewStatus
from memoria_curitibana.domains.archive.schemas.document_schema import (
    DocumentEntitySummary,
    DocumentListResponse,
    DocumentSummary,
    DocumentTagSummary,
)
from memoria_curitibana.domains.archive.services.document_service import DocumentService


@pytest.fixture
def client() -> TestClient:  # type: ignore
    """Provides a test HTTP client for Litestar."""
    with TestClient(app=create_app()) as client:
        yield client  # type: ignore


def _summary(description_id: str = "doc-1") -> DocumentSummary:
    return DocumentSummary(
        description_id=description_id,
        original_title="Título original",
        final_title=None,
        document_date=date(1954, 3, 12),
        review_status=ArchiveReviewStatus.PENDING_AI,
        is_anomaly=False,
        tags=[DocumentTagSummary(tag_id=1, name="urbanismo")],
        entities=[DocumentEntitySummary(entity_id=2, name="Curitiba", entity_type="LOC")],
    )


# ==========================================
# 1. LISTING AND PAGINATION
# ==========================================


def test_list_documents_returns_the_page_envelope(client: TestClient, mocker):
    """The listing is a page: total/limit/offset plus the items."""
    mock_search = mocker.patch.object(DocumentService, "search")
    mock_search.return_value = DocumentListResponse(total=1, limit=50, offset=0, items=[_summary()])

    response = client.get("/api/v1/documents/?limit=50&offset=0")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["items"][0]["description_id"] == "doc-1"
    query = mock_search.call_args.args[0]
    assert (query.term, query.limit, query.offset) == (None, 50, 0)


def test_list_documents_forwards_the_search_term_and_pagination(client: TestClient, mocker):
    """Query parameters must reach the service, not be silently dropped."""
    mock_search = mocker.patch.object(DocumentService, "search")
    mock_search.return_value = DocumentListResponse(total=0, limit=10, offset=20, items=[])

    response = client.get("/api/v1/documents/?term=avenida&limit=10&offset=20")

    assert response.status_code == HTTP_200_OK
    query = mock_search.call_args.args[0]
    assert (query.term, query.limit, query.offset) == ("avenida", 10, 20)


def test_list_documents_forwards_every_facet(client: TestClient, mocker):
    """Facets are part of the HTTP contract, so each one must reach the service."""
    mock_search = mocker.patch.object(DocumentService, "search")
    mock_search.return_value = DocumentListResponse(total=0, limit=50, offset=0, items=[])

    response = client.get(
        "/api/v1/documents/?typology_id=7&macro_category_id=3&entity_type=ORG&date_from=1950-01-01&date_to=1959-12-31"
    )

    assert response.status_code == HTTP_200_OK
    query = mock_search.call_args.args[0]
    assert query.typology_id == 7
    assert query.macro_category_id == 3
    assert query.entity_type == "ORG"
    assert (query.date_from, query.date_to) == (date(1950, 1, 1), date(1959, 12, 31))


# ==========================================
# 2. SINGLE DOCUMENT
# ==========================================


def test_get_document_returns_tags_and_entities(client: TestClient, mocker):
    """The read view carries the taxonomy attached to the document."""
    mock_get = mocker.patch.object(DocumentService, "get")
    mock_get.return_value = _summary("doc-7")

    response = client.get("/api/v1/documents/doc-7")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["description_id"] == "doc-7"
    assert body["document_date"] == "1954-03-12"
    assert body["tags"] == [{"tag_id": 1, "name": "urbanismo"}]
    assert body["entities"] == [{"entity_id": 2, "name": "Curitiba", "entity_type": "LOC"}]
    mock_get.assert_called_once_with("doc-7")


def test_get_missing_document_maps_to_404(client: TestClient, mocker):
    """A domain not-found error becomes 404 through the domain exception handler."""
    mocker.patch.object(DocumentService, "get", side_effect=DocumentNotFoundError("Documento 'x' não encontrado."))

    response = client.get("/api/v1/documents/x")

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "DocumentNotFoundError"


# ==========================================
# 3. HUMAN REVIEW (HITL)
# ==========================================


def test_update_document_sends_only_the_provided_fields(client: TestClient, mocker):
    """`exclude_unset` matters: an absent field must not be sent as None."""
    mock_update = mocker.patch.object(DocumentService, "update_review")
    mock_update.return_value = _summary("doc-9")

    response = client.patch("/api/v1/documents/doc-9", json={"final_title": "Título revisado"})

    assert response.status_code == HTTP_200_OK
    command = mock_update.call_args.args[0]
    assert command.description_id == "doc-9"
    assert command.final_title == "Título revisado"
    # Not sent by the client, so it must not be part of the command payload.
    assert "scope_content" not in command.model_dump(exclude_unset=True)


def test_update_document_rejects_unknown_fields(client: TestClient, mocker):
    """The request model forbids extras instead of silently ignoring a typo."""
    mock_update = mocker.patch.object(DocumentService, "update_review")

    response = client.patch("/api/v1/documents/doc-9", json={"tittle": "typo"})

    assert response.status_code == 400
    mock_update.assert_not_called()
