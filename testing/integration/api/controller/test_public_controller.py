"""HTTP contract of the diffusion surface.

The property that matters here is not "the route works" but "the route cannot be talked out of the
gate": ``published_only`` is set by the controller, never by the client.
"""

import pytest
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND
from litestar.testing import TestClient

from scrinalia.asgi import create_app
from scrinalia.domains.archive.exceptions import DocumentNotFoundError
from scrinalia.domains.archive.models import ArchiveReviewStatus
from scrinalia.domains.archive.schemas.document_schema import (
    DocumentListResponse,
    DocumentMacroCategorySummary,
    DocumentSummary,
    DocumentTagSummary,
)
from scrinalia.domains.archive.services.document_service import DocumentService


@pytest.fixture
def client() -> TestClient:  # type: ignore
    with TestClient(app=create_app()) as client:
        yield client  # type: ignore


def _published_summary(description_id: str = "pub-1") -> DocumentSummary:
    from datetime import date

    return DocumentSummary(
        description_id=description_id,
        original_title="Título",
        final_title="Título final",
        document_date=date(1954, 3, 12),
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
        is_published=True,
        is_anomaly=True,
        anomaly_reasons=["BAD_DATE"],
        archivist_notes="nota interna",
        provenance="doação interna",
        suggested_final_title="sugestão",
        reference_code="BR PR",
        level="Dossiê",
        producers="IPPUC",
        scope_content="Conteúdo",
        tags=[DocumentTagSummary(tag_id=1, name="urbanismo", macro_category_id=4, macro_category_name="Urbanismo")],
        macro_categories=[DocumentMacroCategorySummary(category_id=4, name="Urbanismo", tag_count=1)],
    )


def test_the_public_list_always_applies_the_diffusion_gate(client: TestClient, mocker) -> None:
    """
    The gate is set server-side.

    A client that sends ``published_only=false`` — or anything else — must not be able to ask for
    unpublished records, because the parameter is not part of the public contract at all.
    """
    mock_search = mocker.patch.object(DocumentService, "search")
    mock_search.return_value = DocumentListResponse(total=0, limit=50, offset=0, items=[])

    response = client.get("/api/v1/public/documents?published_only=false&limit=10")

    assert response.status_code == HTTP_200_OK
    query = mock_search.call_args.args[0]
    assert query.published_only is True
    assert query.limit == 10


def test_the_public_list_projects_every_item_through_the_allowlist(client: TestClient, mocker) -> None:
    """What leaves the API is the projection, not the internal read view."""
    mock_search = mocker.patch.object(DocumentService, "search")
    mock_search.return_value = DocumentListResponse(total=1, limit=50, offset=0, items=[_published_summary("pub-9")])

    body = client.get("/api/v1/public/documents").json()

    item = body["items"][0]
    assert item["description_id"] == "pub-9"
    assert item["producers"] == "IPPUC"
    for forbidden in ("review_status", "is_anomaly", "anomaly_reasons", "archivist_notes", "provenance"):
        assert forbidden not in item, f"{forbidden} vazou para a superfície pública"
    # The subject decision is dropped from the tag, while the drawer itself still arrives.
    assert item["tags"] == [{"tag_id": 1, "name": "urbanismo"}]
    assert item["macro_categories"] == [{"category_id": 4, "name": "Urbanismo", "tag_count": 1}]


def test_an_unpublished_document_is_a_404_not_a_403(client: TestClient, mocker) -> None:
    """
    The refusal must not confirm that the record exists.

    A 403 would tell the caller exactly the fact the gate protects: that this description is in the
    archive. The service raises the same not-found error it would for an id that does not exist.
    """
    mock_get = mocker.patch.object(DocumentService, "get_published")
    mock_get.side_effect = DocumentNotFoundError("Documento 'x' não encontrado no acervo.")

    response = client.get("/api/v1/public/documents/x")

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "DocumentNotFoundError"


def test_the_public_surface_exposes_no_write_route() -> None:
    """
    The diffusion app is born open, so its safety is that nothing on it writes.

    Asserted over the real route table rather than by reading the controller: a route added later
    would otherwise be a silent hole.
    """
    app = create_app()
    public_paths = [route.path for route in app.routes if route.path.startswith("/api/v1/public")]

    assert public_paths, "a superfície pública não registrou nenhuma rota"
    write_methods = {"POST", "PATCH", "PUT", "DELETE"}
    for route in app.routes:
        if not route.path.startswith("/api/v1/public"):
            continue
        methods = {method.upper() for method in (route.methods or set())}
        assert not (methods & write_methods), f"{route.path} aceita escrita: {sorted(methods & write_methods)}"
