"""HTTP surface of the diffusion channels (``/api/v1/diffusion``).

The operator screen reads every channel in one request, edits its lifecycle/configuration and its
agenda. Reads are ``AUTHENTICATED``; the writes are ``OPERATE``, because configuring where the archive
goes is the installation's distribution and not a cataloguing decision. The publication itself is
``CURATE`` and lives in #251.

The API only records the channel. The export run and its ledger axis are #212; the ``POST /runs``
route and the ``last_run``/``active_run`` fields arrive with it, not here.
"""

from litestar import Controller, delete, get, patch, put
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath

from scrinalia.api.dependencies import provide_current_user, provide_diffusion_channel_service
from scrinalia.api.security import Access, AuthenticatedUser
from scrinalia.domains.diffusion.schemas import (
    DiffusionChannelDTO,
    DiffusionChannelListResponse,
    DiffusionChannelUpdateRequest,
    DiffusionScheduleRequest,
)
from scrinalia.domains.diffusion.service import DiffusionChannelService


class DiffusionController(Controller):
    path = "/api/v1/diffusion"
    tags = ["Diffusion"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "current_user": Provide(provide_current_user, sync_to_thread=False),
        "diffusion_service": Provide(provide_diffusion_channel_service, sync_to_thread=False),
    }

    @get("/channels", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_channels(
        self, diffusion_service: NamedDependency[DiffusionChannelService]
    ) -> DiffusionChannelListResponse:
        """Every definition the package ships, configured or not, with its effective configuration."""
        return diffusion_service.list_channels()

    @get("/channels/{code:str}", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def get_channel(
        self,
        diffusion_service: NamedDependency[DiffusionChannelService],
        code: FromPath[str],
    ) -> DiffusionChannelDTO:
        """One channel; an unknown code answers 404 with the known ones."""
        return diffusion_service.get_channel(code)

    @patch("/channels/{code:str}", opt={"access": Access.OPERATE}, status_code=200, sync_to_thread=True)
    def update_channel(
        self,
        diffusion_service: NamedDependency[DiffusionChannelService],
        code: FromPath[str],
        data: DiffusionChannelUpdateRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> DiffusionChannelDTO:
        """
        Saves the lifecycle and the channel's own configuration.

        The body is partial on purpose: a pause sends only ``enabled`` and keeps the configuration; a
        configuration form sends only ``config`` and keeps the paused state. The configuration is
        validated by the channel's own model — a title-less site or an invalid URL is a 422, not a
        JSONB the app discovers when it tries to render.
        """
        return diffusion_service.update_channel(code, data, author=current_user.author)

    @put("/channels/{code:str}/schedule", opt={"access": Access.OPERATE}, status_code=200, sync_to_thread=True)
    def put_schedule(
        self,
        diffusion_service: NamedDependency[DiffusionChannelService],
        code: FromPath[str],
        data: DiffusionScheduleRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> DiffusionChannelDTO:
        """Creates or replaces the agenda of an ``EXPORT`` channel; a ``LIVE`` channel answers 422."""
        return diffusion_service.set_schedule(code, data, author=current_user.author)

    @delete("/channels/{code:str}/schedule", opt={"access": Access.OPERATE}, status_code=200, sync_to_thread=True)
    def delete_schedule(
        self,
        diffusion_service: NamedDependency[DiffusionChannelService],
        code: FromPath[str],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> DiffusionChannelDTO:
        """Removes the agenda; the channel keeps its configuration and the runs it already created."""
        return diffusion_service.clear_schedule(code, author=current_user.author)
