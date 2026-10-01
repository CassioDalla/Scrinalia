from litestar import Controller, get, patch
from litestar.di import Provide

from api.dependencies import provide_document_service
from api.schemas.documents import DocumentUpdateRequest
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
        """Lista/pagina o acervo, com busca textual opcional em título e conteúdo."""
        return document_service.search(term=term, limit=limit, offset=offset)

    @get("/{description_id:str}", sync_to_thread=True)
    def get_document(self, document_service: DocumentService, description_id: str) -> DocumentSummary:
        """Retorna um documento específico com suas tags e entidades."""
        return document_service.get(description_id)

    @patch("/{description_id:str}", sync_to_thread=True)
    def update_document(
        self,
        document_service: DocumentService,
        description_id: str,
        data: DocumentUpdateRequest,
    ) -> DocumentSummary:
        """Aplica a revisão humana e marca o documento como HUMAN_APPROVED."""
        return document_service.update_review(description_id, data.model_dump(exclude_unset=True))
