"""Read model and configuration of the AI workers, for the operations panel.

Everything the panel shows is assembled here: the catalogue (from the code), the effective
configuration (precedence + ``describe_config``), the queue numbers (each worker's own predicate)
and the last/active run (the ledger). One request, because nine workers fit in one and a home screen
that needs seven requests is a home screen that lies about being instant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from inspect import signature
from typing import Any

from sqlalchemy.orm import Session

from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.exceptions import WorkerNotFoundError
from memoria_curitibana.domains.archive.models.operations import WorkerSetting
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository
from memoria_curitibana.domains.archive.repository.worker_run_repo import WorkerRunRepository
from memoria_curitibana.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from memoria_curitibana.domains.archive.schemas.system_schema import (
    SystemWorkersResponse,
    WorkerEngineDTO,
    WorkerPresetDTO,
    WorkerSettingsDTO,
    WorkerSettingsRequest,
    WorkerSettingsRevisionDTO,
    WorkerSettingsRevisionListResponse,
    WorkerStatusDTO,
)
from memoria_curitibana.domains.archive.workers.catalogue import (
    WORKER_CATALOGUE,
    WorkerSpec,
    axis_registry,
    count_failed,
    count_pending,
    count_processed,
    worker_module,
)
from memoria_curitibana.domains.archive.workers.configuration import (
    ResolvedWorkerConfig,
    resolve_configuration,
    validate_engine_choice,
    validate_options,
)


class WorkerOperationsService:
    """Builds the panel and owns the settings writes; it never runs a worker."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = WorkerSettingsRepository(db)
        self.runs = WorkerRunRepository(db)

    # --- reads -----------------------------------------------------------------------------------

    def list_workers(self) -> SystemWorkersResponse:
        settings = self.settings.get_all()
        last_runs = self.runs.last_by_worker()
        active_runs = self.runs.active_by_worker()

        workers = []
        for order, spec in enumerate(WORKER_CATALOGUE.values()):
            setting = settings.get(spec.name)
            resolved = resolve_configuration(self.db, spec, setting)
            # Counted once: the transfer's counter validates the whole staging table, so asking it
            # twice (once for the number and once for the reason) would double the panel's cost.
            pending, pending_reason = self._pending(spec, resolved)
            workers.append(
                WorkerStatusDTO(
                    name=spec.name,
                    label=spec.label,
                    description=spec.description,
                    order=order,
                    unit=spec.unit,
                    governed=spec.governed,
                    settings=self._settings_dto(spec, setting, resolved),
                    pending=pending,
                    pending_reason=pending_reason,
                    processed=self._processed(spec, resolved),
                    failed=self._failed(spec, resolved),
                    last_run=last_runs.get(spec.name),
                    active_run=active_runs.get(spec.name),
                )
            )
        return SystemWorkersResponse(workers=workers, generated_at=datetime.now(UTC))

    def get_settings(self, worker_name: str) -> WorkerSettingsDTO:
        spec = self._spec(worker_name)
        setting = self.settings.get(worker_name)
        resolved = resolve_configuration(self.db, spec, setting)
        return self._settings_dto(spec, setting, resolved)

    def list_revisions(self, worker_name: str, *, limit: int, offset: int) -> WorkerSettingsRevisionListResponse:
        self._spec(worker_name)
        rows, total = self.settings.list_revisions(worker_name, limit=limit, offset=offset)
        return WorkerSettingsRevisionListResponse(
            items=[
                WorkerSettingsRevisionDTO(
                    revision_id=row.id,
                    worker_name=row.worker_name,
                    before=row.before,
                    after=row.after,
                    changed_by=row.changed_by,
                    changed_at=row.changed_at,
                )
                for row in rows
            ],
            total=total,
        )

    # --- writes ----------------------------------------------------------------------------------

    def update_settings(self, worker_name: str, request: WorkerSettingsRequest) -> WorkerSettingsDTO:
        spec = self._spec(worker_name)
        validate_engine_choice(spec, request.engine_name, request.preset)
        validate_options(spec, request.options)

        self.settings.upsert(
            worker_name,
            engine_name=request.engine_name,
            preset=request.preset,
            db_batch_size=request.db_batch_size,
            options=request.options,
            changed_by=request.changed_by,
        )
        return self.get_settings(worker_name)

    def clear_settings(self, worker_name: str, *, changed_by: str | None) -> WorkerSettingsDTO:
        spec = self._spec(worker_name)
        self.settings.clear(worker_name, changed_by=changed_by)
        setting = self.settings.get(worker_name)
        return self._settings_dto(spec, setting, resolve_configuration(self.db, spec, setting))

    # --- internals -------------------------------------------------------------------------------

    def _spec(self, worker_name: str) -> WorkerSpec:
        spec = WORKER_CATALOGUE.get(worker_name)
        if spec is None:
            raise WorkerNotFoundError(f"Worker '{worker_name}' não existe. Opções: {sorted(WORKER_CATALOGUE)}.")
        return spec

    def _settings_dto(
        self, spec: WorkerSpec, setting: WorkerSetting | None, resolved: ResolvedWorkerConfig
    ) -> WorkerSettingsDTO:
        return WorkerSettingsDTO(
            worker_name=spec.name,
            engine_name=resolved.engine_name,
            preset=resolved.preset,
            db_batch_size=resolved.db_batch_size,
            options=dict(setting.options or {}) if setting is not None else {},
            overridden=setting is not None,
            updated_by=setting.updated_by if setting is not None else None,
            updated_at=setting.updated_at if setting is not None else None,
            engine_source=spec.engine_source,
            config=resolved.config,
            available_engines=self._available_engines(spec),
            note=self._note(spec, resolved),
        )

    def _available_engines(self, spec: WorkerSpec) -> list[WorkerEngineDTO]:
        if spec.axis is None:
            return []
        registry = axis_registry(spec.axis)
        return [
            WorkerEngineDTO(
                name=engine_name,
                presets=[
                    WorkerPresetDTO(name=preset_name, config=registry.describe_config(engine_name, preset_name))
                    for preset_name in registry.PRESETS
                ],
            )
            for engine_name in registry.AVAILABLE_ENGINES
        ]

    def _note(self, spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> str | None:
        """Dynamic notes the catalogue cannot carry, because they depend on the collection."""
        notes = [spec.note, resolved.note]
        if spec.name == "macro-category" and not TagRepository(self.db).get_active_macro_categories():
            notes.append("Nenhuma gaveta de assunto ativa: o worker não tem o que classificar.")
        present = [note for note in notes if note]
        return " ".join(present) if present else None

    def _counter_options(self, spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> dict[str, Any]:
        """
        Only the options the counter declares.

        The counter is a reader, not the worker: handing it ``columns_to_extract`` is useful,
        handing it a parameter it does not read (or a runner dataclass) is not. The filter is by the
        counter's own signature, so a new counter cannot be broken by an unrelated option.
        """
        counter_name = spec.counter or spec.processed_counter
        if counter_name is None:
            return {}
        parameters = signature(getattr(worker_module(spec.module), counter_name)).parameters
        return {key: value for key, value in resolved.forwarded_options.items() if key in parameters}

    def _pending(self, spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> tuple[int | None, str | None]:
        """The pending number and, when there is none, the reason a person can read."""
        if spec.counter is None:
            return None, spec.unmeasurable_reason
        try:
            return count_pending(spec, self.db, **self._counter_options(spec, resolved)), None
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível contar a fila de '{spec.name}': {exc}")
            return None, "A contagem falhou; veja o log do servidor."

    def _processed(self, spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> int | None:
        if spec.stamp is None and spec.processed_counter is None:
            return None
        try:
            return count_processed(spec, self.db, **self._counter_options(spec, resolved))
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível contar o processado de '{spec.name}': {exc}")
            return None

    def _failed(self, spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> int | None:
        if spec.stamp is None and spec.failed_counter is None:
            return None
        try:
            return count_failed(spec, self.db, **self._counter_options(spec, resolved))
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível contar as falhas de '{spec.name}': {exc}")
            return None
