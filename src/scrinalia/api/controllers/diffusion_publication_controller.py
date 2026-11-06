"""HTTP surface of the publication gesture (``/api/v1/diffusion``, #251).

The reads are ``AUTHENTICATED``: a viewer may see what the institution published and what is waiting.
The three writes are ``CURATE`` — deciding what leaves is the curator's, while configuring where it
can go is the operator's (``/channels``). The preview is ``CURATE`` as well, unlike the catalogue
previews: it is the first half of a publication and its sample is a curation decision, not a dry run.

The channels this controller names are the configured and enabled ones; the service refuses a paused
or unknown channel with a sentence, so the page can show the refusal instead of a silent skip.
"""

from litestar import Controller, get, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from scrinalia.api.dependencies import provide_current_user, provide_diffusion_publication_service
from scrinalia.api.security import Access, AuthenticatedUser
from scrinalia.domains.diffusion.publication_repository import PublicationState
from scrinalia.domains.diffusion.publication_schemas import (
    PublicationApplyRequest,
    PublicationBatchDTO,
    PublicationBatchListDTO,
    PublicationCountsDTO,
    PublicationPageDTO,
    PublicationPreviewDTO,
    PublicationRequest,
    PublicationScopeListDTO,
    PublicationUndoDTO,
)
from scrinalia.domains.diffusion.publication_service import DiffusionPublicationService


class DiffusionPublicationController(Controller):
    path = "/api/v1/diffusion"
    tags = ["Diffusion"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "current_user": Provide(provide_current_user, sync_to_thread=False),
        "publication_service": Provide(provide_diffusion_publication_service, sync_to_thread=False),
    }

    # --- the reads -------------------------------------------------------------------------------

    @get("/publications", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_publications(
        self,
        publication_service: NamedDependency[DiffusionPublicationService],
        publication_state: FromQuery[PublicationState] = "uncovered",
        node_id: FromQuery[str | None] = None,
        channel_code: FromQuery[str | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> PublicationPageDTO:
        """
        The branch's records, split by state: what a channel carries, or the approved without one.

        ``state=uncovered`` is the page's "A publicar" and the home card's count; ``state=covered``
        is "Publicadas". The header's counts travel with either page, from the same definition.
        """
        return publication_service.publications(
            state=publication_state, node_id=node_id, channel_code=channel_code, limit=limit, offset=offset
        )

    @get("/publications/summary", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def summary(self, publication_service: NamedDependency[DiffusionPublicationService]) -> PublicationCountsDTO:
        """
        The four numbers without a page: what the home screen needs and the header repeats.

        A separate route because the home screen asks for the counts and not for a list, and asking
        for a list to read its header would put a page of descriptions on the way to a number.
        """
        return publication_service.summary()

    @get("/scopes", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_scopes(
        self,
        publication_service: NamedDependency[DiffusionPublicationService],
        channel_code: FromQuery[str | None] = None,
    ) -> PublicationScopeListDTO:
        """The active positive and negative scopes, with their node, author and counts."""
        return publication_service.scopes(channel_code)

    @get("/publications/batches", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_batches(
        self,
        publication_service: NamedDependency[DiffusionPublicationService],
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> PublicationBatchListDTO:
        """The publication history, newest first."""
        return publication_service.history(limit, offset)

    # --- the writes ------------------------------------------------------------------------------

    @post("/publications/preview", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def preview(
        self,
        publication_service: NamedDependency[DiffusionPublicationService],
        data: PublicationRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> PublicationPreviewDTO:
        """
        Resolves the gesture per channel and writes nothing.

        The answer is the eligible count, a sample, what each channel skips and why, and the token
        the confirmation must echo. It expires, and the apply re-resolves: a preview is not a promise
        about a collection that keeps changing.
        """
        return publication_service.preview(data)

    @post("/publications", opt={"access": Access.CURATE}, status_code=201, sync_to_thread=True)
    def apply(
        self,
        publication_service: NamedDependency[DiffusionPublicationService],
        data: PublicationApplyRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> PublicationBatchDTO:
        """
        Writes the scopes and the batch; the token is the preview's.

        A stale token is a 409 with "preview again", not a silent apply over a different set.
        """
        return publication_service.apply(data.request, data.token, author=current_user.author)

    @post(
        "/publications/batches/{batch_id:int}/undo", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True
    )
    def undo(
        self,
        publication_service: NamedDependency[DiffusionPublicationService],
        batch_id: FromPath[int],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> PublicationUndoDTO:
        """
        Reverts the batch entry by entry and reports what it left alone.

        A second undo is a 409: after the first, later decisions may sit on top of this one.
        """
        return publication_service.undo(batch_id, author=current_user.author)
