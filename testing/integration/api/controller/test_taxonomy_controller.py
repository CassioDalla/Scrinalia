from datetime import UTC, datetime

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
from memoria_curitibana.domains.archive.exceptions import (
    InvalidMergeError,
    MacroCategoryNotFoundError,
    MergeAlreadyUndoneError,
    MergeLogNotFoundError,
    TagMergeProposalNotFoundError,
    TagNotFoundError,
)
from memoria_curitibana.domains.archive.schemas import ArchiveMacroCategoryEntityDTO
from memoria_curitibana.domains.archive.schemas.entity_schema import NerExclusion
from memoria_curitibana.domains.archive.schemas.tag_schema import (  # <-- Import the DTO
    MergeLogEntryDTO,
    TagMergeProposalDTO,
    TagRelevanceIdf,
)
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


# ==========================================
# 3. MACRO CATEGORIES (SUBJECT AXIS)
# ==========================================


def _category_dto(category_id: int = 1, name: str = "Urbanismo") -> ArchiveMacroCategoryEntityDTO:
    return ArchiveMacroCategoryEntityDTO(category_id=category_id, name=name, description=None, is_active=True)


def test_list_macro_categories_returns_200(client: TestClient, mocker):
    mock_service = mocker.patch.object(TagService, "list_macro_categories")
    mock_service.return_value = [_category_dto()]

    response = client.get("/api/v1/taxonomy/macro-categories?only_active=true")

    assert response.status_code == HTTP_200_OK
    assert response.json()[0]["name"] == "Urbanismo"
    mock_service.assert_called_once_with(only_active=True)


def test_create_macro_category_returns_201(client: TestClient, mocker):
    mock_service = mocker.patch.object(TagService, "create_macro_category")
    mock_service.return_value = _category_dto(category_id=5, name="Saúde")

    response = client.post(
        "/api/v1/taxonomy/macro-categories", json={"name": "Saúde", "description": "Epidemias e hospitais"}
    )

    assert response.status_code == HTTP_201_CREATED
    assert response.json()["category_id"] == 5

    command = mock_service.call_args[0][0]
    assert command.name == "Saúde"
    assert command.description == "Epidemias e hospitais"


def test_update_macro_category_returns_200(client: TestClient, mocker):
    mock_service = mocker.patch.object(TagService, "update_macro_category")
    mock_service.return_value = _category_dto()

    response = client.patch("/api/v1/taxonomy/macro-categories/1", json={"is_active": False})

    assert response.status_code == HTTP_200_OK
    command = mock_service.call_args[0][1]
    # exclude_unset: an absent description must not be sent as None
    assert command.model_dump(exclude_unset=True) == {"is_active": False}


def test_update_macro_category_triggers_404_when_missing(client: TestClient, mocker):
    mock_service = mocker.patch.object(TagService, "update_macro_category")
    mock_service.side_effect = MacroCategoryNotFoundError("Macro categoria 999 não encontrada no acervo.")

    response = client.patch("/api/v1/taxonomy/macro-categories/999", json={"is_active": False})

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "MacroCategoryNotFoundError"


def test_create_macro_category_triggers_409_on_duplicate_name(client: TestClient, mocker):
    mock_service = mocker.patch.object(TagService, "create_macro_category")
    mock_service.side_effect = IntegrityError("statement", "params", "orig")  # type: ignore

    response = client.post("/api/v1/taxonomy/macro-categories", json={"name": "Urbanismo"})

    assert response.status_code == HTTP_409_CONFLICT
    assert response.json()["error_code"] == "IntegrityError"


# ==========================================
# 4. NER EXCLUSIONS (THE SUBJECT AXIS OWNS THE TERM)
# ==========================================


def test_create_ner_exclusions_returns_201(client: TestClient, mocker):
    """The curator bans a term from NER and learns how many entities were purged."""
    mock_service = mocker.patch.object(EntityService, "exclude_terms_from_ner")
    mock_service.return_value = 3

    response = client.post(
        "/api/v1/taxonomy/entities/ner-exclusions",
        json={"words": ["IPTU"], "reason": "é assunto, não entidade"},
    )

    assert response.status_code == HTTP_201_CREATED
    assert response.json()["entities_deleted"] == 3
    mock_service.assert_called_once_with(["IPTU"], reason="é assunto, não entidade")


def test_create_ner_exclusions_rejects_empty_list(client: TestClient, mocker):
    """An empty request cannot silently mean 'ban everything'."""
    mock_service = mocker.patch.object(EntityService, "exclude_terms_from_ner")

    response = client.post("/api/v1/taxonomy/entities/ner-exclusions", json={"words": []})

    assert response.status_code == HTTP_400_BAD_REQUEST
    mock_service.assert_not_called()


def test_list_ner_exclusions_returns_200(client: TestClient, mocker):
    mock_service = mocker.patch.object(EntityService, "list_ner_exclusions")
    mock_service.return_value = [
        NerExclusion(
            term="iptu",
            reason="assunto, não entidade",
            source="JUDGE",
            tag_id=7,
            created_at=datetime(2026, 10, 3, tzinfo=UTC),
        )
    ]

    response = client.get("/api/v1/taxonomy/entities/ner-exclusions")

    assert response.status_code == HTTP_200_OK
    assert response.json()[0]["term"] == "iptu"
    assert response.json()[0]["source"] == "JUDGE"


def test_remove_ner_exclusions_returns_200(client: TestClient, mocker):
    """Undoing the decision re-opens the term for the extractor."""
    mock_service = mocker.patch.object(EntityService, "remove_ner_exclusions")
    mock_service.return_value = 1

    response = client.request(
        "DELETE",
        "/api/v1/taxonomy/entities/ner-exclusions",
        json={"words": ["iptu"]},
    )

    assert response.status_code == HTTP_200_OK
    assert response.json()["removed"] == 1
    mock_service.assert_called_once_with(["iptu"])


# ==========================================
# TAG MERGE PROPOSALS (persisted evidence + decision) AND DRY-RUN
# ==========================================


def _stored_proposal(**overrides) -> "TagMergeProposalDTO":
    from memoria_curitibana.domains.archive.schemas.tag_schema import TagMergeMember, TagMergeProposalDTO

    data = {
        "proposal_id": 7,
        "fingerprint": "fingerprint",
        "canonical_id": 1,
        "canonical_name": "rua",
        "reason": "TRIGRAM",
        "total_documents": 11,
        "review_flags": ["MEMBER_WITH_DIGITS"],
        "status": "SUGGESTED",
        "members": [
            TagMergeMember(tag_id=1, name="rua", document_count=8),
            TagMergeMember(tag_id=2, name="rua 7", document_count=3),
        ],
    }
    data.update(overrides)
    return TagMergeProposalDTO(**data)


def test_suggest_tag_merges_route_registers_the_proposals(client: TestClient, mocker):
    from memoria_curitibana.domains.archive.schemas.tag_schema import MergeSuggestionRunResponse

    mocked = mocker.patch.object(TagService, "suggest_merges")
    mocked.return_value = MergeSuggestionRunResponse(clusters_found=411, persisted=411, pending=411, flagged=60)

    response = client.post("/api/v1/taxonomy/tags/merge-proposals/suggest", json={"threshold": 0.8, "limit": 100})

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["clusters_found"] == 411
    assert body["pending"] == 411
    assert body["flagged"] == 60
    assert mocked.call_args.kwargs == {"threshold": 0.8, "limit": 100}


def test_list_tag_merge_proposals_route_paginates_with_a_total(client: TestClient, mocker):
    from memoria_curitibana.domains.archive.schemas.tag_schema import TagMergeProposalListResponse

    mocked = mocker.patch.object(TagService, "list_merge_proposals")
    mocked.return_value = TagMergeProposalListResponse(total=411, limit=50, offset=0, items=[_stored_proposal()])

    response = client.get("/api/v1/taxonomy/tags/merge-proposals?status=SUGGESTED&flagged_only=true&limit=50")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["total"] == 411
    assert body["items"][0]["canonical_name"] == "rua"
    assert body["items"][0]["members"][1]["name"] == "rua 7"
    assert mocked.call_args.kwargs == {
        "status": "SUGGESTED",
        "reason": None,
        "min_documents": 0,
        "flagged_only": True,
        "limit": 50,
        "offset": 0,
    }


def test_decide_tag_merge_proposal_route_returns_the_verdict(client: TestClient, mocker):
    mocked = mocker.patch.object(TagService, "decide_merge_proposal")
    mocked.return_value = _stored_proposal(status="APPROVED", decided_by="arquivista")

    response = client.patch(
        "/api/v1/taxonomy/tags/merge-proposals/7",
        json={"status": "APPROVED", "decided_by": "arquivista", "note": "mesmo conceito"},
    )

    assert response.status_code == HTTP_200_OK
    assert response.json()["data"]["status"] == "APPROVED"

    proposal_id, command = mocked.call_args[0]
    assert proposal_id == 7
    assert command.status == "APPROVED"
    assert command.decided_by == "arquivista"
    assert command.note == "mesmo conceito"


def test_decide_tag_merge_proposal_route_maps_a_missing_proposal_to_404(client: TestClient, mocker):
    mocker.patch.object(
        TagService, "decide_merge_proposal", side_effect=TagMergeProposalNotFoundError("não encontrada")
    )

    response = client.patch("/api/v1/taxonomy/tags/merge-proposals/999", json={"status": "REJECTED"})

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "TagMergeProposalNotFoundError"


def test_preview_tag_merge_route_returns_the_impact(client: TestClient, mocker):
    from memoria_curitibana.domains.archive.schemas.tag_schema import MergePreviewResponse, TagMergeImpact

    mocked = mocker.patch.object(TagService, "preview_merge")
    mocked.return_value = MergePreviewResponse(
        canonical_id=1,
        canonical_name="rua",
        documents_updated=5,
        links_rewritten=7,
        tags_deleted=[TagMergeImpact(tag_id=2, name="rua 7", document_count=7)],
        synonyms_created=["rua 7"],
        review_flags=["MEMBER_WITH_DIGITS"],
        category_would_be_lost=False,
    )

    response = client.post("/api/v1/taxonomy/tags/merge/preview", json={"proposal_id": 7})

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["documents_updated"] == 5
    assert body["review_flags"] == ["MEMBER_WITH_DIGITS"]
    assert mocked.call_args[0][0].proposal_id == 7


def test_preview_tag_merge_route_rejects_two_sources(client: TestClient):
    response = client.post(
        "/api/v1/taxonomy/tags/merge/preview",
        json={"proposal_id": 7, "canonical_id": 1, "ids_to_merge": [2]},
    )

    assert response.status_code == HTTP_400_BAD_REQUEST


# ==========================================
# BATCH APPLICATION, AUDIT TRAIL AND UNDO (the ledger)
# ==========================================


def _log_entry(**overrides) -> "MergeLogEntryDTO":
    from memoria_curitibana.domains.archive.schemas.tag_schema import MergeLogEntryDTO

    data = {
        "merge_id": 5,
        "cluster_fingerprint": "fp-1",
        "canonical_id": 1,
        "canonical_name": "rua",
        "absorbed_tag_id": 2,
        "absorbed_name": "ruas",
        "document_count": 3,
        "changed_by": "arquivista",
    }
    data.update(overrides)
    return MergeLogEntryDTO(**data)


def test_apply_tag_merge_batch_route_reports_each_cluster(client: TestClient, mocker):
    from memoria_curitibana.domains.archive.schemas.tag_schema import (
        BatchMergeResponse,
        MergeBatchApplied,
        MergeBatchFailure,
    )

    mocked = mocker.patch.object(TagService, "merge_batch")
    mocked.return_value = BatchMergeResponse(
        applied=[MergeBatchApplied(proposal_id=1, merge_ids=[5], documents_updated=2, tags_deleted=1)],
        failed=[MergeBatchFailure(proposal_id=2, error="Proposta rejeitada pelo curador.")],
    )

    response = client.post(
        "/api/v1/taxonomy/tags/merge/batch",
        json={"proposal_ids": [1, 2], "changed_by": "arquivista", "note": "lote"},
    )

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["applied"][0]["merge_ids"] == [5]
    assert body["failed"][0]["proposal_id"] == 2

    command = mocked.call_args[0][0]
    assert command.proposal_ids == [1, 2]
    assert command.changed_by == "arquivista"


def test_list_tag_merge_log_route_paginates(client: TestClient, mocker):
    from memoria_curitibana.domains.archive.schemas.tag_schema import MergeLogListResponse

    mocked = mocker.patch.object(TagService, "list_merge_log")
    mocked.return_value = MergeLogListResponse(total=12, limit=5, offset=0, items=[_log_entry()])

    response = client.get("/api/v1/taxonomy/tags/merge-log?canonical_id=1&include_undone=false&limit=5")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["total"] == 12
    assert body["items"][0]["absorbed_name"] == "ruas"
    assert mocked.call_args.kwargs == {
        "canonical_id": 1,
        "changed_by": None,
        "include_undone": False,
        "limit": 5,
        "offset": 0,
    }


def test_undo_tag_merge_route_returns_the_restored_entry(client: TestClient, mocker):
    mocked = mocker.patch.object(TagService, "undo_merge")
    mocked.return_value = _log_entry(undone_by="arquivista")

    response = client.delete("/api/v1/taxonomy/tags/merge-log/5?undone_by=arquivista")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["data"]["undone_by"] == "arquivista"
    assert "restaurada" in body["message"]
    mocked.assert_called_once_with(5, undone_by="arquivista")


def test_undo_tag_merge_route_maps_a_repeated_undo_to_409(client: TestClient, mocker):
    mocker.patch.object(TagService, "undo_merge", side_effect=MergeAlreadyUndoneError("já desfeita"))

    response = client.delete("/api/v1/taxonomy/tags/merge-log/5")

    assert response.status_code == HTTP_409_CONFLICT
    assert response.json()["error_code"] == "MergeAlreadyUndoneError"


def test_undo_tag_merge_route_maps_an_unknown_merge_to_404(client: TestClient, mocker):
    mocker.patch.object(TagService, "undo_merge", side_effect=MergeLogNotFoundError("não encontrado"))

    response = client.delete("/api/v1/taxonomy/tags/merge-log/999")

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "MergeLogNotFoundError"
