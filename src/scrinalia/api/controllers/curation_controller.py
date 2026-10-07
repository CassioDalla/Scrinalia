from litestar import Controller, get
from litestar.di import NamedDependency, Provide

from scrinalia.api.dependencies import provide_curation_service
from scrinalia.domains.archive.schemas.curation_schema import CurationInbox
from scrinalia.domains.archive.services.curation_service import CurationService


class CurationController(Controller):
    path = "/api/v1/curation"
    tags = ["Curation"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "curation_service": Provide(provide_curation_service, sync_to_thread=False),
    }

    @get("/inbox", sync_to_thread=True)
    def get_inbox(self, curation_service: NamedDependency[CurationService]) -> CurationInbox:
        """
        The curator's work list: what is pending, and which screen resolves it.

        One request instead of one per screen. Every count comes from an indexed column, so the
        home screen stays instant; the queues that are empty are returned with zero rather than
        omitted, because "there is nothing here" is information the archivist needs.
        """
        return curation_service.inbox()
