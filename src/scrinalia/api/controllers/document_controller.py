from datetime import date
from typing import Literal

from litestar import Controller, delete, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from scrinalia.api.dependencies import provide_document_service
from scrinalia.api.schemas.documents import (
    DocumentUpdateRequest,
    EntityLinkRequest,
    TagLinkRequest,
)
from scrinalia.domains.archive.models import ArchiveReviewStatus
from scrinalia.domains.archive.schemas import RouteMessageCode
from scrinalia.domains.archive.schemas.command_schema import (
    DocumentReviewCommand,
    EntityLinkCommand,
    TagLinkCommand,
)
from scrinalia.domains.archive.schemas.document_schema import (
    DocumentDeletionListResponse,
    DocumentDeletionResponse,
    DocumentListResponse,
    DocumentRevisionDTO,
    DocumentSummary,
)
from scrinalia.domains.archive.schemas.query_schema import DocumentSearchQuery
from scrinalia.domains.archive.services.document_service import DocumentService


class DocumentController(Controller):
    path = "/api/v1/documents"
    tags = ["Documents"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "document_service": Provide(provide_document_service, sync_to_thread=False),
    }

    @get("/", sync_to_thread=True)
    def list_documents(
        self,
        document_service: NamedDependency[DocumentService],
        term: FromQuery[str | None] = None,
        mode: FromQuery[Literal["lexical", "semantic"]] = "lexical",
        typology_id: FromQuery[int | None] = None,
        macro_category_id: FromQuery[int | None] = None,
        level_id: FromQuery[int | None] = None,
        ancestor_id: FromQuery[str | None] = None,
        entity_type: FromQuery[str | None] = None,
        date_from: FromQuery[date | None] = None,
        date_to: FromQuery[date | None] = None,
        status: FromQuery[ArchiveReviewStatus | None] = None,
        is_anomaly: FromQuery[bool | None] = None,
        anomaly_reason: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> DocumentListResponse:
        """
        Lists/paginates the collection with full-text or semantic ranking and facet filters.

        ``ancestor_id`` is "search inside this fonds/série": the branch is resolved to its
        materialised path and matched with one indexed prefix, so it costs the same at any depth.
        """
        return document_service.search(
            DocumentSearchQuery(
                term=term,
                mode=mode,
                typology_id=typology_id,
                macro_category_id=macro_category_id,
                level_id=level_id,
                ancestor_id=ancestor_id,
                entity_type=entity_type,
                date_from=date_from,
                date_to=date_to,
                status=status,
                is_anomaly=is_anomaly,
                anomaly_reason=anomaly_reason,
                limit=limit,
                offset=offset,
            )
        )

    @get("/deletions", sync_to_thread=True)
    def list_deletions(
        self,
        document_service: NamedDependency[DocumentService],
        term: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> DocumentDeletionListResponse:
        """
        The deletion ledger: what was removed, when, by whom and the snapshot of it.

        It is a ledger and not a revision because the revision table cascades with the document — an
        audit trail of a deletion has to outlive the thing it describes.
        """
        return document_service.list_deletions(term=term, limit=limit, offset=offset)

    @get("/{description_id:str}", sync_to_thread=True)
    def get_document(
        self, document_service: NamedDependency[DocumentService], description_id: FromPath[str]
    ) -> DocumentSummary:
        """Returns a specific document with its tags and entities."""
        return document_service.get(description_id)

    @get("/{description_id:str}/revisions", sync_to_thread=True)
    def list_revisions(
        self, document_service: NamedDependency[DocumentService], description_id: FromPath[str]
    ) -> list[DocumentRevisionDTO]:
        """Human review audit trail: who changed what, and from which value to which."""
        return document_service.list_revisions(description_id)

    @patch("/{description_id:str}", sync_to_thread=True)
    def update_document(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        data: DocumentUpdateRequest,
    ) -> DocumentSummary:
        """Applies the human review, records the changes and marks the document HUMAN_APPROVED."""
        return document_service.update_review(
            DocumentReviewCommand(description_id=description_id, **data.model_dump(exclude_unset=True))
        )

    # --- Local subject curation ---------------------------------------------------------------
    #
    # Until now "this document is about this too" could only be decided by merging terms globally or
    # by re-running a worker. These four routes close that gap, and they follow the same rule as the
    # field edit: a human decision is recorded in the revision ledger and takes the record out of
    # the AI's reach.
    @post("/{description_id:str}/tags", status_code=201, sync_to_thread=True)
    def link_tag(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        data: TagLinkRequest,
    ) -> DocumentSummary:
        """Attaches one tag to this description, records the revision and marks it HUMAN_APPROVED."""
        return document_service.link_tag(
            TagLinkCommand(description_id=description_id, tag_id=data.tag_id), data.changed_by, data.review_note
        )

    @delete("/{description_id:str}/tags/{tag_id:int}", status_code=200, sync_to_thread=True)
    def unlink_tag(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        tag_id: FromPath[int],
        changed_by: FromQuery[str | None] = None,
        review_note: FromQuery[str | None] = None,
    ) -> DocumentSummary:
        """Detaches one tag from this description, records the revision and marks it HUMAN_APPROVED."""
        return document_service.unlink_tag(
            TagLinkCommand(description_id=description_id, tag_id=tag_id), changed_by, review_note
        )

    @post("/{description_id:str}/entities", status_code=201, sync_to_thread=True)
    def link_entity(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        data: EntityLinkRequest,
    ) -> DocumentSummary:
        """Attaches one named entity to this description, records the revision and marks it HUMAN_APPROVED."""
        return document_service.link_entity(
            EntityLinkCommand(description_id=description_id, entity_id=data.entity_id),
            data.changed_by,
            data.review_note,
        )

    @delete("/{description_id:str}/entities/{entity_id:int}", status_code=200, sync_to_thread=True)
    def unlink_entity(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        entity_id: FromPath[int],
        changed_by: FromQuery[str | None] = None,
        review_note: FromQuery[str | None] = None,
    ) -> DocumentSummary:
        """Detaches one named entity from this description, records the revision and marks it HUMAN_APPROVED."""
        return document_service.unlink_entity(
            EntityLinkCommand(description_id=description_id, entity_id=entity_id), changed_by, review_note
        )

    # --- Deletion ------------------------------------------------------------------------------
    #
    # The one write on this controller that removes a record. It refuses a node with children (the
    # arrangement's FK is RESTRICT on purpose) and records the snapshot before deleting, so the
    # decision can be explained afterwards.
    @delete("/{description_id:str}", status_code=200, sync_to_thread=True)
    def delete_document(
        self,
        document_service: NamedDependency[DocumentService],
        description_id: FromPath[str],
        changed_by: FromQuery[str | None] = None,
        note: FromQuery[str | None] = None,
    ) -> DocumentDeletionResponse:
        """Deletes one description, refusing a node that still has children below it."""
        entry = document_service.delete(description_id, changed_by=changed_by, note=note)
        return DocumentDeletionResponse(
            code=RouteMessageCode.DOCUMENT_DELETED,
            message=f"Descrição '{entry.title}' excluída do acervo.",
            data=entry,
        )
