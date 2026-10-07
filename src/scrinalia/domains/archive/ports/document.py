from typing import Protocol

from scrinalia.domains.archive.schemas.command_schema import (
    DocumentReviewCommand,
    EntityLinkCommand,
    TagLinkCommand,
)
from scrinalia.domains.archive.schemas.document_schema import (
    ArchiveDocumentDTO,
    DocumentDeletionDTO,
    DocumentFacets,
    DocumentRevisionDTO,
    DocumentSummary,
)
from scrinalia.domains.archive.schemas.query_schema import DocumentSearchQuery


class DocumentRepositoryPort(Protocol):
    """
    Output port for the Archive document (fact table).

    Reads return ``DocumentSummary`` DTOs and writes take DTOs/commands, so the
    SQLAlchemy entity never crosses the boundary.
    """

    # --- Read (showcase / curation) ---
    def search(
        self, query: DocumentSearchQuery, query_embedding: list[float] | None = None
    ) -> tuple[list[DocumentSummary], int, DocumentFacets]: ...
    def get_by_id(self, description_id: str) -> DocumentSummary | None: ...
    def fetch_documents_for_clustering(self, columns_to_extract: list[str] | None = None) -> list[str]: ...
    def list_revisions(self, description_id: str) -> list[DocumentRevisionDTO]: ...
    def count_children(self, description_id: str) -> int: ...
    def list_deletions(self, term: str | None, limit: int, offset: int) -> tuple[list[DocumentDeletionDTO], int]: ...

    # --- Write ---
    def upsert_archive_document(self, doc_data: ArchiveDocumentDTO) -> bool: ...
    def update_review(self, command: DocumentReviewCommand) -> DocumentSummary | None: ...
    def link_tag(
        self, command: TagLinkCommand, changed_by: str | None = None, note: str | None = None
    ) -> DocumentSummary | None: ...
    def unlink_tag(
        self, command: TagLinkCommand, changed_by: str | None = None, note: str | None = None
    ) -> DocumentSummary | None: ...
    def link_entity(
        self, command: EntityLinkCommand, changed_by: str | None = None, note: str | None = None
    ) -> DocumentSummary | None: ...
    def unlink_entity(
        self, command: EntityLinkCommand, changed_by: str | None = None, note: str | None = None
    ) -> DocumentSummary | None: ...
    def delete_document(
        self, description_id: str, changed_by: str | None = None, note: str | None = None
    ) -> DocumentDeletionDTO | None: ...
