from typing import Protocol

from domains.archive.schemas.document_schema import ArchiveDocumentDTO, DocumentSummary


class DocumentRepositoryPort(Protocol):
    """
    Output port for the Archive document (fact table).

    Read methods return ``DocumentSummary`` DTOs. Write methods (``upsert``,
    ``update_review``, ``stamp_ai_execution``) still operate on the ORM entity:
    returning command/result DTOs on the write side is a known debt
    (see `.analysis/adr-arquitetura-alvo.md`).
    """

    # --- Read (showcase / curation) ---
    def search(
        self, term: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[DocumentSummary], int]: ...
    def get_by_id(self, description_id: str) -> DocumentSummary | None: ...
    def fetch_documents_for_clustering(self, columns_to_extract: list[str] | None = None) -> list[str]: ...

    # --- Write ---
    def upsert_archive_document(self, doc_data: ArchiveDocumentDTO) -> bool: ...
    def update_review(self, description_id: str, changes: dict) -> DocumentSummary | None: ...
    def stamp_ai_execution(self, description_id: str, worker_name: str) -> None: ...
