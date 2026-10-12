from typing import Protocol

from scrinalia.core.author import Author
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
    ) -> tuple[list[DocumentSummary], int, DocumentFacets]:
        raise NotImplementedError

    def get_by_id(self, description_id: str) -> DocumentSummary | None:
        raise NotImplementedError

    def fetch_documents_for_clustering(self, columns_to_extract: list[str] | None = None) -> list[str]:
        raise NotImplementedError

    def list_revisions(self, description_id: str) -> list[DocumentRevisionDTO]:
        raise NotImplementedError

    def count_children(self, description_id: str) -> int:
        raise NotImplementedError

    def list_deletions(self, term: str | None, limit: int, offset: int) -> tuple[list[DocumentDeletionDTO], int]:
        raise NotImplementedError

    # --- Write ---
    def upsert_archive_document(self, doc_data: ArchiveDocumentDTO) -> bool:
        raise NotImplementedError

    def update_review(self, command: DocumentReviewCommand) -> DocumentSummary | None:
        raise NotImplementedError

    def link_tag(
        self, command: TagLinkCommand, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentSummary | None:
        raise NotImplementedError

    def unlink_tag(
        self, command: TagLinkCommand, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentSummary | None:
        raise NotImplementedError

    def link_entity(
        self, command: EntityLinkCommand, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentSummary | None:
        raise NotImplementedError

    def unlink_entity(
        self, command: EntityLinkCommand, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentSummary | None:
        raise NotImplementedError

    def delete_document(
        self, description_id: str, changed_by: Author | None = None, note: str | None = None
    ) -> DocumentDeletionDTO | None:
        raise NotImplementedError
