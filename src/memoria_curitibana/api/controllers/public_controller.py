"""Diffusion surface: the same domain services, a deliberately narrower contract.

Two properties make this surface different from the curator's, and both are structural rather than
procedural:

* every field it returns is declared in ``api/schemas/public.py``, so a new internal field cannot
  leak by default;
* it never accepts the diffusion gate as input. ``published_only`` is set **here**, server-side, so
  no query string can ask for an unpublished record. A route that forgot to set it would be a bug,
  not a client's choice.

There is no authentication here on purpose: this surface is born open, and the boundary being
protected is *what data exists*, not who is asking (ADR 0003).
"""

from datetime import date
from typing import Literal

from litestar import Controller, get
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from memoria_curitibana.api.dependencies import provide_document_service
from memoria_curitibana.api.schemas.public import (
    PublicDocumentFacets,
    PublicDocumentListResponse,
    PublicDocumentSummary,
)
from memoria_curitibana.domains.archive.schemas.query_schema import DocumentSearchQuery
from memoria_curitibana.domains.archive.services.document_service import DocumentService


class PublicController(Controller):
    path = "/api/v1/public"
    tags = ["Public"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "document_service": Provide(provide_document_service, sync_to_thread=False),
    }

    @get("/documents", sync_to_thread=True)
    def list_published(
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
    ) -> PublicDocumentListResponse:
        """Searches the diffused collection. Records not cleared for publication are simply absent."""
        page = document_service.search(
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
                # Server-side, never a query parameter: the public cannot ask for more.
                published_only=True,
                limit=limit,
                offset=offset,
            )
        )
        return PublicDocumentListResponse(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[PublicDocumentSummary.from_summary(item) for item in page.items],
            facets=PublicDocumentFacets.from_facets(page.facets),
        )

    @get("/documents/{description_id:str}", sync_to_thread=True)
    def get_published(
        self, document_service: NamedDependency[DocumentService], description_id: FromPath[str]
    ) -> PublicDocumentSummary:
        """
        One diffused description.

        An unpublished record answers **404**, not 403: refusing with a distinct status would
        confirm that the description exists, which is the fact the gate is protecting.
        """
        return PublicDocumentSummary.from_summary(document_service.get_published(description_id))
