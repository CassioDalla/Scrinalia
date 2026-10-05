from datetime import date
from typing import Literal

from litestar import Controller, get, patch
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from memoria_curitibana.api.dependencies import provide_document_service
from memoria_curitibana.api.schemas.documents import DocumentUpdateRequest
from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand
from memoria_curitibana.domains.archive.schemas.document_schema import (
    DocumentListResponse,
    DocumentRevisionDTO,
    DocumentSummary,
)
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery
from memoria_curitibana.domains.archive.services.document_service import DocumentService


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
                limit=limit,
                offset=offset,
            )
        )

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
