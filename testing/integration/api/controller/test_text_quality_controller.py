"""HTTP contract of the text-template curation controller."""

import pytest
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)
from litestar.testing import TestClient

from memoria_curitibana.asgi import create_app
from memoria_curitibana.domains.archive.exceptions import TextTemplateNotFoundError
from memoria_curitibana.domains.archive.schemas import RouteMessageCode
from memoria_curitibana.domains.archive.schemas.text_quality_schema import (
    TemplateDryRunResponse,
    TemplateSuggestionResponse,
    TextTemplateDTO,
)
from memoria_curitibana.domains.archive.services.text_quality_service import TextQualityService

BLOCK = "Acervo de 35.327 fotografias que retratam a cidade de Curitiba no âmbito do Planejamento"


@pytest.fixture
def client() -> TestClient:  # type: ignore
    with TestClient(app=create_app()) as client:
        yield client  # type: ignore


def _template(template_id: int = 1, **overrides) -> TextTemplateDTO:
    data = {
        "template_id": template_id,
        "text": BLOCK,
        "fingerprint": "f" * 64,
        "status": "SUGGESTED",
        "source": "SUGGESTED",
        "is_active": False,
        "occurrence_count": 2467,
        "sample_document_ids": ["doc-1"],
    }
    data.update(overrides)
    return TextTemplateDTO(**data)


# ==========================================
# LISTING
# ==========================================


def test_list_serialises_the_catalog(client: TestClient, mocker) -> None:
    mocker.patch.object(TextQualityService, "list_templates", return_value=[_template(1), _template(2)])

    response = client.get("/api/v1/quality/text-templates/")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert [row["template_id"] for row in body] == [1, 2]
    assert body[0]["occurrence_count"] == 2467


def test_list_forwards_the_filters(client: TestClient, mocker) -> None:
    mocked = mocker.patch.object(TextQualityService, "list_templates", return_value=[])

    client.get("/api/v1/quality/text-templates/?status=APPROVED&only_active=true")

    assert mocked.call_args.kwargs == {"status": "APPROVED", "only_active": True}


# ==========================================
# SUGGESTION
# ==========================================


def test_suggest_returns_the_candidates(client: TestClient, mocker) -> None:
    mocked = mocker.patch.object(
        TextQualityService,
        "suggest_templates",
        return_value=TemplateSuggestionResponse(
            documents_scanned=3608,
            candidates=[],
            persisted=0,
            code=RouteMessageCode.TEXT_TEMPLATE_SUGGESTED,
            message="nada aplicado",
        ),
    )

    response = client.post("/api/v1/quality/text-templates/suggest", json={"min_ratio": 0.1, "min_documents": 3})

    assert response.status_code == HTTP_201_CREATED
    assert response.json()["documents_scanned"] == 3608
    assert mocked.call_args.kwargs == {"min_ratio": 0.1, "min_documents": 3}


def test_suggest_rejects_a_ratio_above_one(client: TestClient, mocker) -> None:
    mocked = mocker.patch.object(TextQualityService, "suggest_templates")

    response = client.post("/api/v1/quality/text-templates/suggest", json={"min_ratio": 2})

    assert response.status_code == HTTP_400_BAD_REQUEST
    mocked.assert_not_called()


# ==========================================
# DRY RUN
# ==========================================


def test_preview_translates_the_request_into_the_domain_dto(client: TestClient, mocker) -> None:
    mocked = mocker.patch.object(
        TextQualityService, "dry_run", return_value=TemplateDryRunResponse(documents_affected=1, documents_scanned=10)
    )

    response = client.post(
        "/api/v1/quality/text-templates/preview",
        json={"text": "  bloco   repetido ", "variants": ["outra grafia"], "sample_limit": 2},
    )

    assert response.status_code == HTTP_201_CREATED
    dto = mocked.call_args.args[0]
    assert dto.text == "  bloco   repetido "
    assert dto.variants == ["outra grafia"]
    assert dto.action == "IGNORE"
    assert dto.sample_limit == 2


# ==========================================
# CREATION AND DECISIONS
# ==========================================


def test_create_returns_the_row_and_the_requeued_count(client: TestClient, mocker) -> None:
    mocked = mocker.patch.object(
        TextQualityService, "create_template", return_value=(_template(7, status="APPROVED", is_active=True), 12)
    )

    response = client.post(
        "/api/v1/quality/text-templates/",
        json={"text": BLOCK, "changed_by": "ana", "reason": "bloco do acervo"},
    )

    assert response.status_code == HTTP_201_CREATED
    body = response.json()
    assert body["documents_requeued"] == 12
    assert body["data"]["template_id"] == 7
    assert "Trecho cadastrado" in body["message"]
    command = mocked.call_args.args[0]
    assert command.created_by == "ana"
    assert command.reason == "bloco do acervo"


def test_create_rejects_an_unknown_field(client: TestClient, mocker) -> None:
    mocked = mocker.patch.object(TextQualityService, "create_template")

    response = client.post("/api/v1/quality/text-templates/", json={"text": BLOCK, "scope": "DEFAULT"})

    assert response.status_code == HTTP_400_BAD_REQUEST
    mocked.assert_not_called()


def test_update_approves_and_reports_the_requeue(client: TestClient, mocker) -> None:
    mocked = mocker.patch.object(
        TextQualityService,
        "update_template",
        return_value=(_template(3, status="APPROVED", is_active=True), 4),
    )

    response = client.patch("/api/v1/quality/text-templates/3", json={"status": "APPROVED", "changed_by": "ana"})

    assert response.status_code == HTTP_200_OK
    assert response.json()["documents_requeued"] == 4
    assert response.json()["data"]["status"] == "APPROVED"
    command = mocked.call_args.args[1]
    assert command.status == "APPROVED"
    assert command.changed_by == "ana"


def test_update_missing_template_maps_to_404(client: TestClient, mocker) -> None:
    mocker.patch.object(
        TextQualityService,
        "update_template",
        side_effect=TextTemplateNotFoundError("Trecho 99 não encontrado no catálogo."),
    )

    response = client.patch("/api/v1/quality/text-templates/99", json={"status": "REJECTED"})

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error_code"] == "TextTemplateNotFoundError"


def test_delete_undoes_and_reports_the_requeue(client: TestClient, mocker) -> None:
    mocked = mocker.patch.object(
        TextQualityService, "delete_template", return_value=(_template(5, status="APPROVED"), 30)
    )

    response = client.delete("/api/v1/quality/text-templates/5")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["documents_requeued"] == 30
    assert body["data"]["template_id"] == 5
    mocked.assert_called_once_with(5)


def test_delete_missing_template_maps_to_404(client: TestClient, mocker) -> None:
    mocker.patch.object(
        TextQualityService,
        "delete_template",
        side_effect=TextTemplateNotFoundError("Trecho 99 não encontrado no catálogo."),
    )

    response = client.delete("/api/v1/quality/text-templates/99")

    assert response.status_code == HTTP_404_NOT_FOUND
