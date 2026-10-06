"""HTTP surface of the operations panel (``/api/v1/system``).

Read the workers and their queues, change a worker's persisted defaults, trigger a run and read the
ledger. The probes are the one place where the API talks to something other than PostgreSQL (Ollama
and the object storage), and each of them answers on its own.
"""

from litestar import Controller, delete, get, post, put
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from memoria_curitibana.api.dependencies import provide_worker_operations_service, provide_worker_run_service
from memoria_curitibana.api.system_health import probe_infrastructure
from memoria_curitibana.domains.archive.models.enums import WorkerRunStatus
from memoria_curitibana.domains.archive.schemas.system_schema import (
    SystemHealthResponse,
    SystemWorkersResponse,
    WorkerRunDTO,
    WorkerRunListResponse,
    WorkerRunRequest,
    WorkerSettingsDTO,
    WorkerSettingsRequest,
    WorkerSettingsRevisionListResponse,
)
from memoria_curitibana.domains.archive.services.worker_operations_service import WorkerOperationsService
from memoria_curitibana.domains.archive.services.worker_run_service import WorkerRunService


class SystemController(Controller):
    path = "/api/v1/system"
    tags = ["System"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "operations_service": Provide(provide_worker_operations_service, sync_to_thread=False),
        "run_service": Provide(provide_worker_run_service, sync_to_thread=False),
    }

    @get("/workers", sync_to_thread=True)
    def list_workers(self, operations_service: NamedDependency[WorkerOperationsService]) -> SystemWorkersResponse:
        """
        The whole panel in one request: nine workers with configuration, queues and last run.

        One request because nine rows fit in one, and because a home screen that needs seven of them
        ends up showing numbers from seven different moments.
        """
        return operations_service.list_workers()

    @get("/runs", sync_to_thread=True)
    def list_runs(
        self,
        run_service: NamedDependency[WorkerRunService],
        worker: FromQuery[str | None] = None,
        status: FromQuery[WorkerRunStatus | None] = None,
        limit: FromQuery[int] = 20,
        offset: FromQuery[int] = 0,
    ) -> WorkerRunListResponse:
        """The execution ledger, newest first; ``worker`` and ``status`` narrow it server-side."""
        return run_service.list_runs(worker_name=worker, status=status, limit=limit, offset=offset)

    @post("/workers/{worker_name:str}/runs", status_code=201, sync_to_thread=True)
    def trigger_run(
        self,
        run_service: NamedDependency[WorkerRunService],
        worker_name: FromPath[str],
        data: WorkerRunRequest,
    ) -> WorkerRunDTO:
        """
        Queues one run and answers immediately.

        The body carries overrides for **this** run only; the persisted defaults are the settings
        route. A worker that already has a run in flight answers 409 — the guarantee comes from the
        partial unique index, not from a check the API could race.
        """
        return run_service.trigger(worker_name, data)

    @put("/workers/{worker_name:str}/settings", status_code=200, sync_to_thread=True)
    def update_settings(
        self,
        operations_service: NamedDependency[WorkerOperationsService],
        worker_name: FromPath[str],
        data: WorkerSettingsRequest,
    ) -> WorkerSettingsDTO:
        """Persists the default engine/preset/batch/options of one worker."""
        return operations_service.update_settings(worker_name, data)

    @delete("/workers/{worker_name:str}/settings", status_code=200, sync_to_thread=True)
    def clear_settings(
        self,
        operations_service: NamedDependency[WorkerOperationsService],
        worker_name: FromPath[str],
        changed_by: FromQuery[str | None] = None,
    ) -> WorkerSettingsDTO:
        """Drops the override so the worker follows the code again; idempotent."""
        return operations_service.clear_settings(worker_name, changed_by=changed_by)

    @get("/workers/{worker_name:str}/settings/revisions", sync_to_thread=True)
    def list_settings_revisions(
        self,
        operations_service: NamedDependency[WorkerOperationsService],
        worker_name: FromPath[str],
        limit: FromQuery[int] = 20,
        offset: FromQuery[int] = 0,
    ) -> WorkerSettingsRevisionListResponse:
        """Who changed what, when — an audit trail nobody can read is half a feature."""
        return operations_service.list_revisions(worker_name, limit=limit, offset=offset)

    @get("/health", sync_to_thread=True)
    def health(self) -> SystemHealthResponse:
        """Database, Ollama (with the models the presets need), object storage and the process."""
        return probe_infrastructure()
