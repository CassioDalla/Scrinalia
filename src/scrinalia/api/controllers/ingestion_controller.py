"""HTTP surface of the ingestion origins (``/api/v1/ingestion``).

The screen reads every origin in one request, edits the lifecycle/configuration and the agenda, and
enqueues one execution. The manual form is a separate write with its own permission: a curator may
type a record (``CURATE``), while changing an origin's URLs or schedule and starting a crawl belong
to the operator (``OPERATE``).

The API only enqueues. The ``ingestion`` run is a row in the same ledger the AI workers use; a
runner claims it, and the origin's configuration is read again by the job (ADR 0014/0016).
"""

from litestar import Controller, delete, get, patch, post, put
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath

from scrinalia.api.dependencies import provide_current_user, provide_ingestion_origin_service
from scrinalia.api.security import Access, AuthenticatedUser
from scrinalia.domains.archive.schemas.system_schema import WorkerRunDTO
from scrinalia.domains.ingestion.schemas import (
    CsvImportRequest,
    CsvImportResponse,
    CsvImportSpecResponse,
    IngestionOriginDTO,
    IngestionOriginListResponse,
    IngestionOriginUpdateRequest,
    IngestionRunRequest,
    IngestionScheduleRequest,
    ManualIngestionRequest,
    ManualIngestionResponse,
    build_csv_import_spec,
)
from scrinalia.domains.ingestion.service import IngestionOriginService


class IngestionController(Controller):
    path = "/api/v1/ingestion"
    tags = ["Ingestion"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "current_user": Provide(provide_current_user, sync_to_thread=False),
        "origin_service": Provide(provide_ingestion_origin_service, sync_to_thread=False),
    }

    @get("/origins", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_origins(self, origin_service: NamedDependency[IngestionOriginService]) -> IngestionOriginListResponse:
        """Every origin the package ships, with its queue, its last run and its agenda."""
        return origin_service.list_origins()

    @get("/origins/{code:str}", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def get_origin(
        self,
        origin_service: NamedDependency[IngestionOriginService],
        code: FromPath[str],
    ) -> IngestionOriginDTO:
        """One origin; an unknown code answers 404 with the known ones."""
        return origin_service.get_origin(code)

    @patch("/origins/{code:str}", opt={"access": Access.OPERATE}, status_code=200, sync_to_thread=True)
    def update_origin(
        self,
        origin_service: NamedDependency[IngestionOriginService],
        code: FromPath[str],
        data: IngestionOriginUpdateRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> IngestionOriginDTO:
        """
        Saves the lifecycle and the adapter configuration (URLs, espera).

        The configuration is validated by the origin's own model: a URL that is not a URL is a 422,
        not a JSONB the next run discovers at 02:00.
        """
        return origin_service.update_origin(code, data, author=current_user.author)

    @put("/origins/{code:str}/schedule", opt={"access": Access.OPERATE}, status_code=200, sync_to_thread=True)
    def put_schedule(
        self,
        origin_service: NamedDependency[IngestionOriginService],
        code: FromPath[str],
        data: IngestionScheduleRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> IngestionOriginDTO:
        """Creates or replaces the origin's cron in an explicit IANA zone."""
        return origin_service.set_schedule(code, data, author=current_user.author)

    @delete("/origins/{code:str}/schedule", opt={"access": Access.OPERATE}, status_code=200, sync_to_thread=True)
    def delete_schedule(
        self,
        origin_service: NamedDependency[IngestionOriginService],
        code: FromPath[str],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> IngestionOriginDTO:
        """Removes the agenda; the origin keeps its configuration and the runs it already created."""
        return origin_service.clear_schedule(code, author=current_user.author)

    @post("/origins/{code:str}/runs", opt={"access": Access.OPERATE}, status_code=201, sync_to_thread=True)
    def trigger_origin(
        self,
        origin_service: NamedDependency[IngestionOriginService],
        code: FromPath[str],
        data: IngestionRunRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> WorkerRunDTO:
        """
        Enqueues one ingestion execution for the origin.

        The body overrides the origin's persisted options for this run only. A second execution of
        the same origin while one is in flight answers 409 — the partial unique index includes the
        origin, not the button.
        """
        return origin_service.trigger(code, data, requested_by=current_user.author)

    @post("/manual", opt={"access": Access.CURATE}, status_code=201, sync_to_thread=True)
    def create_manual(
        self,
        origin_service: NamedDependency[IngestionOriginService],
        data: ManualIngestionRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> ManualIngestionResponse:
        """
        Writes one typed record as the manual origin's raw payload and stages it.

        The record is **not** approved by being typed: it is ``PENDING_AI`` in the archive and the
        AI queues see it. The transfer is enqueued immediately; if one is already in flight, the
        response says the record enters the next one.
        """
        return origin_service.create_manual(data, author=current_user.author)

    @get("/csv/spec", opt={"access": Access.AUTHENTICATED}, sync_to_thread=False)
    def csv_import_spec(self) -> CsvImportSpecResponse:
        """
        The CSV map and its bounds, for the screen to parse and validate before sending.

        It is the same catalogue the import route validates against and the staging transform reads,
        so the headers the card offers cannot drift from the ones the API accepts. A read, and it
        needs no session beyond the one every route has.
        """
        return build_csv_import_spec()

    @post("/csv", opt={"access": Access.CURATE}, status_code=200, sync_to_thread=True)
    def import_csv(
        self,
        origin_service: NamedDependency[IngestionOriginService],
        data: CsvImportRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> CsvImportResponse:
        """
        Writes a bounded list of CSV rows, stages the accepted ones and queues one transfer.

        The file is parsed in the browser: no multipart, no object storage, no temporary file. The
        API re-validates every row and answers a per-row report — a partial import is a normal
        outcome, not a 500. A row whose id already exists is reported as duplicated, never written.
        """
        return origin_service.import_csv(data, author=current_user.author)
