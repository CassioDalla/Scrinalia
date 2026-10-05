from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from memoria_curitibana.domains.archive.exceptions import DocumentNotFoundError
from memoria_curitibana.domains.archive.models import ArchiveReviewStatus
from memoria_curitibana.domains.archive.repository import DocumentRepository
from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand
from memoria_curitibana.domains.archive.schemas.document_schema import DocumentFacets, DocumentListResponse
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery
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
    repo.search.return_value = ([_fake_doc("doc-1"), _fake_doc("doc-2")], 2, DocumentFacets())
    service = DocumentService(repo)

    query = DocumentSearchQuery(term="x", limit=10, offset=5)
    result = service.search(query)

    repo.search.assert_called_once_with(query, query_embedding=None)
    assert isinstance(result, DocumentListResponse)
    assert result.total == 2
    assert result.limit == 10
    assert result.offset == 5
    assert [item.description_id for item in result.items] == ["doc-1", "doc-2"]


def test_lexical_search_never_builds_the_embedding_engine() -> None:
    """A lexical request must not pay the cost of loading the embedding model."""
    repo = Mock(spec=DocumentRepository)
    repo.search.return_value = ([], 0, DocumentFacets())
    embedder = Mock()
    service = DocumentService(repo, embedder=embedder)

    service.search(DocumentSearchQuery(term="matadouro"))

    embedder.assert_not_called()
    assert repo.search.call_args.kwargs["query_embedding"] is None


def test_semantic_search_embeds_the_term_and_passes_the_vector() -> None:
    repo = Mock(spec=DocumentRepository)
    repo.search.return_value = ([], 0, DocumentFacets())
    engine = Mock()
    engine.embed.return_value = [[0.1, 0.2]]
    embedder = Mock(return_value=engine)
    service = DocumentService(repo, embedder=embedder)

    service.search(DocumentSearchQuery(term="enchentes", mode="semantic"))

    engine.embed.assert_called_once_with(["enchentes"])
    assert repo.search.call_args.kwargs["query_embedding"] == [0.1, 0.2]


def test_semantic_search_builds_the_engine_only_once() -> None:
    repo = Mock(spec=DocumentRepository)
    repo.search.return_value = ([], 0, DocumentFacets())
    engine = Mock()
    engine.embed.return_value = [[0.0]]
    embedder = Mock(return_value=engine)
    service = DocumentService(repo, embedder=embedder)

    service.search(DocumentSearchQuery(term="a", mode="semantic"))
    service.search(DocumentSearchQuery(term="b", mode="semantic"))

    embedder.assert_called_once()


def test_semantic_search_without_an_embedder_fails_loudly() -> None:
    service = DocumentService(Mock(spec=DocumentRepository))

    with pytest.raises(RuntimeError, match="embedding engine"):
        service.search(DocumentSearchQuery(term="x", mode="semantic"))


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
