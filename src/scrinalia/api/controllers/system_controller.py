"""HTTP surface of the operations panel (``/api/v1/system``).

Read the workers and their queues, change a worker's persisted defaults, trigger a run and read the
ledger. The probes are the one place where the API talks to something other than PostgreSQL (Ollama
and the object storage), and each of them answers on its own.
"""

from litestar import Controller, delete, get, post, put
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from scrinalia.api.dependencies import (
    provide_current_user,
    provide_failure_service,
    provide_worker_operations_service,
    provide_worker_run_service,
)
from scrinalia.api.security import Access, AuthenticatedUser
from scrinalia.api.system_health import probe_infrastructure
from scrinalia.domains.archive.models.enums import WorkerRunStatus
from scrinalia.domains.archive.schemas.system_schema import (
    FailureGroupListResponse,
    SystemHealthResponse,
    SystemWorkerSettingsResponse,
    SystemWorkersResponse,
    WorkerRunDTO,
    WorkerRunListResponse,
    WorkerRunRequest,
    WorkerSettingsDTO,
    WorkerSettingsRequest,
    WorkerSettingsRevisionListResponse,
)
from scrinalia.domains.archive.services.failure_service import FailureService
from scrinalia.domains.archive.services.worker_operations_service import WorkerOperationsService
from scrinalia.domains.archive.services.worker_run_service import WorkerRunService


class SystemController(Controller):
    path = "/api/v1/system"
    tags = ["System"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "current_user": Provide(provide_current_user, sync_to_thread=False),
        "operations_service": Provide(provide_worker_operations_service, sync_to_thread=False),
        "run_service": Provide(provide_worker_run_service, sync_to_thread=False),
        "failure_service": Provide(provide_failure_service, sync_to_thread=False),
    }

    @get("/workers", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_workers(self, operations_service: NamedDependency[WorkerOperationsService]) -> SystemWorkersResponse:
        """
        The whole panel in one request: nine workers with configuration, queues and last run.

        One request because nine rows fit in one, and because a home screen that needs seven of them
        ends up showing numbers from seven different moments.
        """
        return operations_service.list_workers()

    @get("/workers/settings", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_worker_settings(
        self, operations_service: NamedDependency[WorkerOperationsService]
    ) -> SystemWorkerSettingsResponse:
        """
        The persisted defaults of every worker — the configuration screen's read.

        Declared before ``/workers/{worker_name}/settings/revisions`` on purpose, and apart from
        ``/workers``: this route answers *what the installation is set to do*, and the panel answers
        *what the machine is doing*, with nine queue counts this one does not pay for.
        """
        return operations_service.list_settings()

    @get("/runs", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_runs(
        self,
        run_service: NamedDependency[WorkerRunService],
        worker: FromQuery[str | None] = None,
        status: FromQuery[WorkerRunStatus | None] = None,
        fingerprint: FromQuery[str | None] = None,
        limit: FromQuery[int] = 20,
        offset: FromQuery[int] = 0,
    ) -> WorkerRunListResponse:
        """
        The execution ledger, newest first; the filters narrow it server-side.

        ``fingerprint`` is the other end of the failures screen: a group says *what* is breaking, and
        this is how the archivist sees the executions behind it.
        """
        return run_service.list_runs(
            worker_name=worker, status=status, fingerprint=fingerprint, limit=limit, offset=offset
        )

    @get("/failures", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_failures(
        self,
        failure_service: NamedDependency[FailureService],
        days: FromQuery[int] = 30,
        worker: FromQuery[str | None] = None,
        limit: FromQuery[int] = 20,
    ) -> FailureGroupListResponse:
        """
        What is breaking, grouped by root cause — across the executions ledger and the API's own.

        The grouping key is the fingerprint PostgreSQL computes from the error text, so a cause that
        broke a worker **and** a request appears once, with ``sources`` saying where it was seen.
        """
        return failure_service.list_groups(days=days, worker=worker, limit=limit)

    @post("/workers/{worker_name:str}/runs", opt={"access": Access.OPERATE}, status_code=201, sync_to_thread=True)
    def trigger_run(
        self,
        run_service: NamedDependency[WorkerRunService],
        worker_name: FromPath[str],
        data: WorkerRunRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> WorkerRunDTO:
        """
        Queues one run and answers immediately.

        The body carries overrides for **this** run only; the persisted defaults are the settings
        route. A worker that already has a run in flight answers 409 — the guarantee comes from the
        partial unique index, not from a check the API could race.
        """
        return run_service.trigger(worker_name, data, requested_by=current_user.author)

    @put("/workers/{worker_name:str}/settings", opt={"access": Access.OPERATE}, status_code=200, sync_to_thread=True)
    def update_settings(
        self,
        operations_service: NamedDependency[WorkerOperationsService],
        worker_name: FromPath[str],
        data: WorkerSettingsRequest,
        current_user: NamedDependency[AuthenticatedUser],
    ) -> WorkerSettingsDTO:
        """Persists the default engine/preset/batch/options of one worker."""
        return operations_service.update_settings(worker_name, data, changed_by=current_user.author)

    @delete("/workers/{worker_name:str}/settings", opt={"access": Access.OPERATE}, status_code=200, sync_to_thread=True)
    def clear_settings(
        self,
        operations_service: NamedDependency[WorkerOperationsService],
        worker_name: FromPath[str],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> WorkerSettingsDTO:
        """Drops the override so the worker follows the code again; idempotent."""
        return operations_service.clear_settings(worker_name, changed_by=current_user.author)

    @get("/workers/{worker_name:str}/settings/revisions", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def list_settings_revisions(
        self,
        operations_service: NamedDependency[WorkerOperationsService],
        worker_name: FromPath[str],
        limit: FromQuery[int] = 20,
        offset: FromQuery[int] = 0,
    ) -> WorkerSettingsRevisionListResponse:
        """Who changed what, when — an audit trail nobody can read is half a feature."""
        return operations_service.list_revisions(worker_name, limit=limit, offset=offset)

    @get("/health", opt={"access": Access.OPERATE}, sync_to_thread=True)
    def health(self) -> SystemHealthResponse:
        """Database, Ollama (with the models the presets need), object storage and the process."""
        return probe_infrastructure()
