from typing import Protocol

from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand
from memoria_curitibana.domains.archive.schemas.document_schema import ArchiveDocumentDTO, DocumentSummary
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery


class DocumentRepositoryPort(Protocol):
    """
    Output port for the Archive document (fact table).

    Reads return ``DocumentSummary`` DTOs and writes take DTOs/commands, so the
    SQLAlchemy entity never crosses the boundary.
    """

    # --- Read (showcase / curation) ---
    def search(self, query: DocumentSearchQuery) -> tuple[list[DocumentSummary], int]: ...
    def get_by_id(self, description_id: str) -> DocumentSummary | None: ...
    def fetch_documents_for_clustering(self, columns_to_extract: list[str] | None = None) -> list[str]: ...

    # --- Write ---
    def upsert_archive_document(self, doc_data: ArchiveDocumentDTO) -> bool: ...
    def update_review(self, command: DocumentReviewCommand) -> DocumentSummary | None: ...
