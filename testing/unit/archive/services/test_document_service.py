from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from memoria_curitibana.domains.archive.exceptions import DocumentNotFoundError
from memoria_curitibana.domains.archive.models import ArchiveReviewStatus
from memoria_curitibana.domains.archive.repository import DocumentRepository
from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand
from memoria_curitibana.domains.archive.schemas.document_schema import DocumentListResponse
from memoria_curitibana.domains.archive.services.document_service import DocumentService


def _fake_doc(description_id: str = "doc-1", **overrides) -> SimpleNamespace:
    base: dict = {
        "description_id": description_id,
        "original_title": "Título",
        "final_title": None,
        "document_date": None,
        "review_status": ArchiveReviewStatus.PENDING_AI,
        "is_anomaly": False,
        "storage_thumbnail_uri": None,
        "scope_content": "Resumo",
        "admin_bio_history": None,
        "tags": [],
        "entities": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_search_maps_repository_results() -> None:
    repo = Mock(spec=DocumentRepository)
    repo.search.return_value = ([_fake_doc("doc-1"), _fake_doc("doc-2")], 2)
    service = DocumentService(repo)

    result = service.search(term="x", limit=10, offset=5)

    repo.search.assert_called_once_with(term="x", limit=10, offset=5)
    assert isinstance(result, DocumentListResponse)
    assert result.total == 2
    assert [item.description_id for item in result.items] == ["doc-1", "doc-2"]


def test_get_raises_when_missing() -> None:
    repo = Mock(spec=DocumentRepository)
    repo.get_by_id.return_value = None
    service = DocumentService(repo)

    with pytest.raises(DocumentNotFoundError):
        service.get("nao-existe")


def test_update_review_marks_human_approved() -> None:
    repo = Mock(spec=DocumentRepository)
    repo.update_review.return_value = _fake_doc(
        "doc-3", review_status=ArchiveReviewStatus.HUMAN_APPROVED, final_title="Novo"
    )
    service = DocumentService(repo)

    command = DocumentReviewCommand(description_id="doc-3", final_title="Novo")
    result = service.update_review(command)

    repo.update_review.assert_called_once_with(command)
    assert result.review_status == ArchiveReviewStatus.HUMAN_APPROVED
    assert result.final_title == "Novo"
