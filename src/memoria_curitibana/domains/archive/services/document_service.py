from memoria_curitibana.domains.archive.exceptions import DocumentNotFoundError
from memoria_curitibana.domains.archive.ports.document import DocumentRepositoryPort
from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand
from memoria_curitibana.domains.archive.schemas.document_schema import (
    DocumentListResponse,
    DocumentSummary,
)
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery


class DocumentService:
    """
    Service for reading and human curation of the collection (Archive layer).

    Isolates the API and the front-end from direct database access: all
    navigation (showcase) and human editing go through here.
    """

    def __init__(self, repo: DocumentRepositoryPort) -> None:
        self.repo = repo

    def search(self, query: DocumentSearchQuery) -> DocumentListResponse:
        docs, total = self.repo.search(query)
        return DocumentListResponse(total=total, limit=query.limit, offset=query.offset, items=list(docs))

    def get(self, description_id: str) -> DocumentSummary:
        doc = self.repo.get_by_id(description_id)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{description_id}' não encontrado no acervo.")
        return doc

    def update_review(self, command: DocumentReviewCommand) -> DocumentSummary:
        doc = self.repo.update_review(command)
        if doc is None:
            raise DocumentNotFoundError(f"Documento '{command.description_id}' não encontrado no acervo.")
        return doc
