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

from litestar import Controller, get
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from scrinalia.api.dependencies import provide_diffusion_channel_service, provide_document_service
from scrinalia.api.schemas.public import (
    PublicDocumentFacets,
    PublicDocumentListResponse,
    PublicDocumentSummary,
)
from scrinalia.api.security import Access
from scrinalia.domains.archive.schemas.query_schema import DocumentSearchQuery, SearchMode
from scrinalia.domains.archive.services.document_service import DocumentService
from scrinalia.domains.diffusion.diffusion_registry import PUBLIC_SITE_CODE, PublicSiteConfig
from scrinalia.domains.diffusion.service import DiffusionChannelService


class PublicController(Controller):
    path = "/api/v1/public"
    tags = ["Public"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "document_service": Provide(provide_document_service, sync_to_thread=False),
        "diffusion_service": Provide(provide_diffusion_channel_service, sync_to_thread=False),
    }

    @get("/documents", opt={"access": Access.PUBLIC}, sync_to_thread=True)
    def list_published(
        self,
        document_service: NamedDependency[DocumentService],
        diffusion_service: NamedDependency[DiffusionChannelService],
        term: FromQuery[str | None] = None,
        mode: FromQuery[SearchMode] = "lexical",
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
        diffusion_service.require_enabled(PUBLIC_SITE_CODE)
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
                publication_channel=PUBLIC_SITE_CODE,
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

    @get("/documents/{description_id:str}", opt={"access": Access.PUBLIC}, sync_to_thread=True)
    def get_published(
        self,
        document_service: NamedDependency[DocumentService],
        diffusion_service: NamedDependency[DiffusionChannelService],
        description_id: FromPath[str],
    ) -> PublicDocumentSummary:
        """
        One diffused description.

        An unpublished record answers **404**, not 403: refusing with a distinct status would
        confirm that the description exists, which is the fact the gate is protecting.
        """
        diffusion_service.require_enabled(PUBLIC_SITE_CODE)
        return PublicDocumentSummary.from_summary(document_service.get_published(description_id, PUBLIC_SITE_CODE))

    @get("/site", opt={"access": Access.PUBLIC}, sync_to_thread=True)
    def get_site(self, diffusion_service: NamedDependency[DiffusionChannelService]) -> PublicSiteConfig:
        """
        The public site's identity, read before the app's first document query.

        It carries no record and no internal field. **404** while the ``public_site`` channel is not
        configured or is paused: as far as a visitor is concerned, the site is not there.
        """
        return diffusion_service.public_site()
