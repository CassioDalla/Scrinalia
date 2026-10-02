from litestar import Controller, get, patch
from litestar.di import Provide

from api.dependencies import provide_document_service
from api.schemas.documents import DocumentUpdateRequest
from domains.archive.schemas.command_schema import DocumentReviewCommand
from domains.archive.schemas.document_schema import DocumentListResponse, DocumentSummary
from domains.archive.services.document_service import DocumentService


class DocumentController(Controller):
    path = "/api/v1/documents"
    tags = ["Documents"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "document_service": Provide(provide_document_service),
    }

    @get("/", sync_to_thread=True)
    def list_documents(
        self,
        document_service: DocumentService,
        term: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> DocumentListResponse:
        """Lists/paginates the collection, with optional textual search on title and content."""
        return document_service.search(term=term, limit=limit, offset=offset)

    @get("/{description_id:str}", sync_to_thread=True)
    def get_document(self, document_service: DocumentService, description_id: str) -> DocumentSummary:
        """Returns a specific document with its tags and entities."""
        return document_service.get(description_id)

    @patch("/{description_id:str}", sync_to_thread=True)
    def update_document(
        self,
        document_service: DocumentService,
        description_id: str,
        data: DocumentUpdateRequest,
    ) -> DocumentSummary:
        """Applies the human review and marks the document as HUMAN_APPROVED."""
        return document_service.update_review(
            DocumentReviewCommand(description_id=description_id, **data.model_dump(exclude_unset=True))
        )
