"""HTTP contract of the documents controller.

The service is mocked on purpose: these tests pin the HTTP surface (status codes,
envelopes, parameter wiring), while the behaviour behind it is covered by the
service and repository suites.
"""

from datetime import UTC, date, datetime

from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT
from litestar.testing import TestClient

from scrinalia.domains.archive.exceptions import DocumentHasChildrenError, DocumentNotFoundError
from scrinalia.domains.archive.models import ArchiveReviewStatus
from scrinalia.domains.archive.schemas.document_schema import (
    DocumentDeletionDTO,
    DocumentDeletionListResponse,
    DocumentEntitySummary,
    DocumentListResponse,
    DocumentSummary,
    DocumentTagSummary,
)
from scrinalia.domains.archive.services.document_service import DocumentService


def _summary(description_id: str = "doc-1") -> DocumentSummary:
    return DocumentSummary(
        description_id=description_id,
        original_title="Título original",
        final_title=None,
        document_date=date(1954, 3, 12),
        review_status=ArchiveReviewStatus.PENDING_AI,
        is_anomaly=False,
        tags=[
            DocumentTagSummary(
                tag_id=1,
                name="urbanismo",
                macro_category_id=4,
                macro_category_name="Urbanismo",
                ai_confidence_score=0.91,
            )
        ],
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
    assert query.mode == "lexical"


def test_list_documents_forwards_the_search_mode(client: TestClient, mocker):
    """The semantic mode is part of the HTTP contract."""
    mock_search = mocker.patch.object(DocumentService, "search")
    mock_search.return_value = DocumentListResponse(total=0, limit=50, offset=0, items=[])

    response = client.get("/api/v1/documents/?term=enchentes&mode=semantic")

    assert response.status_code == HTTP_200_OK
    assert mock_search.call_args.args[0].mode == "semantic"


def test_list_documents_rejects_an_unknown_mode(client: TestClient, mocker):
    """An unsupported mode must be a 400, not a silent fallback."""
    mock_search = mocker.patch.object(DocumentService, "search")

    response = client.get("/api/v1/documents/?mode=telepatia")

    assert response.status_code == 400
    mock_search.assert_not_called()


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
    """
    The read view carries the taxonomy attached to the document.

    The tag carries its subject decision (macro category and the classifier's confidence) and not
    just the name: the subject tab has to explain *why* a document is filed where it is, and
    resolving that per tag would be an N+1 on the front-end.
    """
    mock_get = mocker.patch.object(DocumentService, "get")
    mock_get.return_value = _summary("doc-7")

    response = client.get("/api/v1/documents/doc-7")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["description_id"] == "doc-7"
    assert body["document_date"] == "1954-03-12"
    assert body["tags"] == [
        {
            "tag_id": 1,
            "name": "urbanismo",
            "macro_category_id": 4,
            "macro_category_name": "Urbanismo",
            "ai_confidence_score": 0.91,
        }
    ]
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


# ==========================================
# HUMAN CURATION: WIDE PATCH AND AUDIT TRAIL
# ==========================================


def test_patch_accepts_any_isad_g_field_and_the_author(client: TestClient, mocker):
    """The archivist fixes the whole record, not only the title."""
    mock_update = mocker.patch.object(DocumentService, "update_review")
    mock_update.return_value = _summary("doc-1")

    response = client.patch(
        "/api/v1/documents/doc-1",
        json={
            "document_date": "1954-03-15",
            "reference_code": "BR PR IPPUC",
            "level_id": 5,
            "provenance": "IPPUC",
            "changed_by": "ana",
            "review_note": "Data conferida no original",
        },
    )

    assert response.status_code == HTTP_200_OK
    command = mock_update.call_args.args[0]
    assert command.document_date == date(1954, 3, 15)
    assert command.reference_code == "BR PR IPPUC"
    assert command.level_id == 5
    assert command.changed_by == "ana"
    assert command.review_note == "Data conferida no original"
    # Fields the client did not send stay unset, so the audit trail ignores them.
    assert command.original_title is None


def test_patch_rejects_an_unknown_field(client: TestClient, mocker):
    mock_update = mocker.patch.object(DocumentService, "update_review")

    response = client.patch("/api/v1/documents/doc-1", json={"review_status": "HUMAN_APPROVED"})

    assert response.status_code == 400
    mock_update.assert_not_called()


def test_list_revisions_serialises_the_trail(client: TestClient, mocker):
    from datetime import UTC, datetime

    from scrinalia.domains.archive.schemas.document_schema import DocumentRevisionDTO

    mocked = mocker.patch.object(DocumentService, "list_revisions")
    mocked.return_value = [
        DocumentRevisionDTO(
            revision_id=2,
            changed_by="ana",
            changes={"original_title": {"old": "A", "new": "B"}},
            note="correção",
            created_at=datetime(2026, 10, 4, 12, 0, tzinfo=UTC),
        )
    ]

    response = client.get("/api/v1/documents/doc-1/revisions")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body[0]["changed_by"] == "ana"
    assert body[0]["changes"]["original_title"]["new"] == "B"
    mocked.assert_called_once_with("doc-1")


# ==========================================
# DELETION AND ITS LEDGER
# ==========================================


def test_delete_document_answers_the_ledger_entry(client: TestClient, mocker) -> None:
    """The route answers what was recorded, not the document that no longer exists."""
    entry = DocumentDeletionDTO(
        deletion_id=7,
        description_id="doc-9",
        reference_code="BR PRADAP IPPUC FOTOGRAFIA 00575",
        title="Praça Castro Alves",
        level_name="Item Documental",
        snapshot={"original_title": "Praça Castro Alves"},
        deleted_by="cassio",
        note="duplicata",
        deleted_at=datetime(2026, 10, 6, 12, 0, tzinfo=UTC),
    )
    mock_delete = mocker.patch.object(DocumentService, "delete")
    mock_delete.return_value = entry

    response = client.delete("/api/v1/documents/doc-9?changed_by=cassio&note=duplicata")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["data"]["deletion_id"] == 7
    assert body["data"]["snapshot"]["original_title"] == "Praça Castro Alves"
    assert "Praça Castro Alves" in body["message"]
    assert mock_delete.call_args.args[:1] == ("doc-9",)
    assert mock_delete.call_args.kwargs == {"changed_by": "cassio", "note": "duplicata"}


def test_delete_document_refuses_a_node_with_children(client: TestClient, mocker) -> None:
    """The arrangement's integrity is a 409, not a 500 from the foreign key."""
    mocker.patch.object(
        DocumentService,
        "delete",
        side_effect=DocumentHasChildrenError("'doc-1' tem 2 descrição(ões) abaixo dela."),
    )

    response = client.delete("/api/v1/documents/doc-1")

    assert response.status_code == HTTP_409_CONFLICT
    assert response.json()["error_code"] == "DocumentHasChildrenError"


def test_delete_document_answers_404_for_a_missing_id(client: TestClient, mocker) -> None:
    """Deleting what is not there is the same 404 as reading it."""
    mocker.patch.object(
        DocumentService, "delete", side_effect=DocumentNotFoundError("Documento 'x' não encontrado no acervo.")
    )

    response = client.delete("/api/v1/documents/x")

    assert response.status_code == HTTP_404_NOT_FOUND


def test_the_deletion_ledger_is_a_page_with_a_search(client: TestClient, mocker) -> None:
    """``term``, ``limit`` and ``offset`` must reach the service, not be silently dropped."""
    mock_list = mocker.patch.object(DocumentService, "list_deletions")
    mock_list.return_value = DocumentDeletionListResponse(total=0, limit=10, offset=20, items=[])

    response = client.get("/api/v1/documents/deletions?term=praca&limit=10&offset=20")

    assert response.status_code == HTTP_200_OK
    assert mock_list.call_args.kwargs == {"term": "praca", "limit": 10, "offset": 20}


def test_the_ledger_route_is_not_read_as_a_description_id(client: TestClient, mocker) -> None:
    """``/documents/deletions`` is static and must win over ``/documents/{description_id}``."""
    mock_list = mocker.patch.object(DocumentService, "list_deletions")
    mock_list.return_value = DocumentDeletionListResponse(total=0, limit=50, offset=0, items=[])
    mock_get = mocker.patch.object(DocumentService, "get")

    response = client.get("/api/v1/documents/deletions")

    assert response.status_code == HTTP_200_OK
    mock_get.assert_not_called()
