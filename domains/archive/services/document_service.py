from domains.archive.exceptions import DocumentNotFoundError
from domains.archive.repository import DocumentRepository
from domains.archive.schemas.document_schema import (
    DocumentListResponse,
    DocumentSummary,
)


class DocumentService:
    """
    Service for reading and human curation of the collection (Archive layer).

    Isolates the API and the front-end from direct database access: all
    navigation (showcase) and human editing go through here.
    """

    def __init__(self, repo: DocumentRepository) -> None:
        self.repo = repo

    def search(self, term: str | None = None, limit: int = 50, offset: int = 0) -> DocumentListResponse:
        docs, total = self.repo.search(term=term, limit=limit, offset=offset)
        return DocumentListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=[DocumentSummary.model_validate(doc) for doc in docs],
        )

    def get(self, description_id: str) -> DocumentSummary:
        doc = self.repo.get_by_id(description_id)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{description_id}' não encontrado no acervo.")
        return DocumentSummary.model_validate(doc)

    def update_review(self, description_id: str, changes: dict) -> DocumentSummary:
        doc = self.repo.update_review(description_id, changes)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{description_id}' não encontrado no acervo.")
        return DocumentSummary.model_validate(doc)
