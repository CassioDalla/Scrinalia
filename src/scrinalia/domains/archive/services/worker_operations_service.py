"""Read model and configuration of the AI workers, for the operations panel.

Everything the panel shows is assembled here: the catalogue (from the code), the effective
configuration (precedence + ``describe_config``), the queue numbers (each worker's own predicate)
and the last/active run (the ledger). One request, because nine workers fit in one and a home screen
that needs seven requests is a home screen that lies about being instant.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.core.i18n import t
from scrinalia.core.logger import logger
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError, WorkerNotFoundError
from scrinalia.domains.archive.models.operations import WorkerSetting
from scrinalia.domains.archive.repository.tag_repo import TagRepository
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.repository.worker_runner_repo import WorkerRunnerRepository
from scrinalia.domains.archive.repository.worker_schedule_repo import WorkerScheduleRepository
from scrinalia.domains.archive.repository.worker_settings_repo import WorkerSettingsRepository
from scrinalia.domains.archive.repository.worker_stamp_repo import StampBreakdown, WorkerStampRepository
from scrinalia.domains.archive.schemas.system_schema import (
    SystemWorkerSettingsResponse,
    SystemWorkersResponse,
    WorkerEngineDTO,
    WorkerOptionDTO,
    WorkerQueuePreviewDTO,
    WorkerSettingsDTO,
    WorkerSettingsItemDTO,
    WorkerSettingsRequest,
    WorkerSettingsRevisionDTO,
    WorkerSettingsRevisionListResponse,
    WorkerStampBreakdownDTO,
    WorkerStatusDTO,
)
from scrinalia.domains.archive.services.worker_schedule_service import to_schedule_dto
from scrinalia.domains.archive.workers.catalogue import (
    WORKER_CATALOGUE,
    WorkerSpec,
    count_failed,
    count_pending,
    count_processed,
    describe_axis_engines,
    engine_option_names,
)
from scrinalia.domains.archive.workers.configuration import (
    ResolvedWorkerConfig,
    counter_options,
    declared_options,
    resolve_configuration,
    validate_engine_choice,
    validate_settings_options,
)


class WorkerOperationsService:
    """Builds the panel and owns the settings writes; it never runs a worker."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = WorkerSettingsRepository(db)
        self.runs = WorkerRunRepository(db)
        self.runner_registry = WorkerRunnerRepository(db)

    # --- reads -----------------------------------------------------------------------------------

    def list_workers(self) -> SystemWorkersResponse:
        last_runs = self.runs.last_by_worker()
        active_runs = self.runs.active_by_worker()
        runners = self.runner_registry.list_for_panel()
        online = [runner for runner in runners if runner.online]
        schedules = {schedule.worker_name: schedule for schedule in WorkerScheduleRepository(self.db).list_all()}

        workers = []
        for order, spec, setting, resolved in self._resolved_workers():
            # Counted once: the transfer's counter validates the whole staging table, so asking it
            # twice (once for the number and once for the reason) would double the panel's cost.
            pending, pending_reason = self._pending(spec, resolved)
            # And once for the whole ledger: the four numbers of a stamp come from one aggregate, and
            # ``processed``/``failed`` are read out of it instead of from two further queries.
            breakdown = self._stamp_breakdown(spec)
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
                    processed=self._processed(spec, resolved, breakdown),
                    failed=self._failed(spec, resolved, breakdown),
                    stamp_breakdown=self._breakdown_dto(breakdown),
                    last_run=last_runs.get(spec.name),
                    active_run=active_runs.get(spec.name),
                    schedule=(to_schedule_dto(schedules[spec.name]) if spec.name in schedules else None),
                    # The API only enqueues; this is the panel's answer to "will anyone pick it up?".
                    runner_available=any(spec.name in runner.capabilities for runner in online),
                )
            )
        return SystemWorkersResponse(workers=workers, runners=runners, generated_at=datetime.now(UTC))

    def list_settings(self) -> SystemWorkerSettingsResponse:
        """
        The persisted defaults of every worker, assembled without touching a queue.

        A reader of its own and not a filter over ``list_workers``: that one counts nine queues, and
        the transfer's counter validates the whole staging table. The configuration screen shows no
        queue, so paying for them would be paying for what it deliberately does not say.
        """
        workers = [
            WorkerSettingsItemDTO(
                name=spec.name,
                label=spec.label,
                description=spec.description,
                order=order,
                settings=self._settings_dto(spec, setting, resolved),
            )
            for order, spec, setting, resolved in self._resolved_workers()
            # The ingestion stage has no engine and its options live on the origin row; a settings
            # card here would be a second place to configure the same crawl (ADR 0016).
            if not spec.origin_axis
        ]
        return SystemWorkerSettingsResponse(workers=workers, generated_at=datetime.now(UTC))

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

    def preview_queue(self, worker_name: str, request: WorkerSettingsRequest) -> WorkerQueuePreviewDTO:
        """
        The pending count of a **proposed** configuration, computed without writing anything.

        A queue keyed on the producer identity makes a settings change re-queue units, so the
        archivist has to be able to read that number before saving it — the plan that precedes the
        write. The resolution is the one a run uses (explicit argument over persisted override over
        signature default), so the preview cannot disagree with the run it announces.
        """
        spec = self._spec(worker_name)
        # The body is a **settings** body: the preview answers what saving it would cost, so it
        # refuses what the save refuses (a run-only option has no default to preview).
        validate_settings_options(spec, request.options)
        setting = self.settings.get(worker_name)
        resolved = resolve_configuration(
            self.db,
            spec,
            setting,
            engine_name=request.engine_name,
            preset=request.preset,
            db_batch_size=request.db_batch_size,
            options=request.options,
        )
        pending, reason = self._pending(spec, resolved)
        return WorkerQueuePreviewDTO(worker_name=worker_name, pending=pending, pending_reason=reason)

    # --- writes ----------------------------------------------------------------------------------

    def update_settings(
        self, worker_name: str, request: WorkerSettingsRequest, *, changed_by: Author | None = None
    ) -> WorkerSettingsDTO:
        spec = self._spec(worker_name)
        validate_engine_choice(spec, request.engine_name, request.preset)
        validate_settings_options(spec, request.options)

        self.settings.upsert(
            worker_name,
            engine_name=request.engine_name,
            preset=request.preset,
            db_batch_size=request.db_batch_size,
            options=request.options,
            changed_by=changed_by,
        )
        return self.get_settings(worker_name)

    def clear_settings(self, worker_name: str, *, changed_by: Author | None) -> WorkerSettingsDTO:
        spec = self._spec(worker_name)
        self.settings.clear(worker_name, changed_by=changed_by)
        setting = self.settings.get(worker_name)
        return self._settings_dto(spec, setting, resolve_configuration(self.db, spec, setting))

    # --- internals -------------------------------------------------------------------------------

    def _resolved_workers(self) -> Iterator[tuple[int, WorkerSpec, WorkerSetting | None, ResolvedWorkerConfig]]:
        """
        The catalogue in order: each worker with its persisted row and its resolved configuration.

        One traversal for both readers. The panel and the configuration screen differ in what they do
        with the pair, not in how it is resolved, and a second copy would be a second place to forget
        a worker that stopped following the code.
        """
        settings = self.settings.get_all()
        for order, spec in enumerate(WORKER_CATALOGUE.values()):
            setting = settings.get(spec.name)
            yield order, spec, setting, resolve_configuration(self.db, spec, setting)

    def _spec(self, worker_name: str) -> WorkerSpec:
        spec = WORKER_CATALOGUE.get(worker_name)
        if spec is None:
            raise WorkerNotFoundError(
                t(
                    "Worker '{worker_name}' não existe. Opções: {worker_catalogue}.",
                    worker_name=worker_name,
                    worker_catalogue=sorted(WORKER_CATALOGUE),
                )
            )
        if spec.origin_axis:
            raise InvalidWorkerSettingsError(
                t("A ingestão não tem engine nem padrão de worker: a configuração dela é a da origem.")
            )
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
            trial_supported=spec.trial,
            config=resolved.config,
            available_engines=self._available_engines(spec),
            declared_options=self._declared_options(spec),
            engine_option_names=list(engine_option_names(spec)),
            note=self._note(spec, resolved),
        )

    def _declared_options(self, spec: WorkerSpec) -> list[WorkerOptionDTO]:
        """The options the worker declares, as the screen renders them."""
        return [
            WorkerOptionDTO(
                name=option.name,
                kind=option.kind,
                scope=option.scope,
                default=option.default,
                choices=list(option.choices),
            )
            for option in declared_options(spec)
        ]

    def _available_engines(self, spec: WorkerSpec) -> list[WorkerEngineDTO]:
        return describe_axis_engines(spec.axis) if spec.axis is not None else []

    def _note(self, spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> str | None:
        """Dynamic notes the catalogue cannot carry, because they depend on the collection."""
        notes = [spec.note, resolved.note]
        if spec.name == "macro-category" and not TagRepository(self.db).get_active_macro_categories():
            notes.append("Nenhuma categoria de assunto ativa: o worker não tem o que classificar.")
        present = [note for note in notes if note]
        return " ".join(present) if present else None

    def _pending(self, spec: WorkerSpec, resolved: ResolvedWorkerConfig) -> tuple[int | None, str | None]:
        """The pending number and, when there is none, the reason a person can read."""
        if spec.counter is None:
            return None, spec.unmeasurable_reason
        try:
            return count_pending(spec, self.db, **counter_options(spec, resolved)), None
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível contar a fila de '{spec.name}': {exc}")
            return None, "A contagem falhou; veja o log do servidor."

    def _stamp_breakdown(self, spec: WorkerSpec) -> StampBreakdown | None:
        """
        The four numbers of a stamped ledger, or ``None`` when the worker's ledger is not a stamp.

        One read for the whole row: ``processed``, ``failed`` and the breakdown the screen shows all
        come from this object, so a stamped worker costs one aggregate instead of the two a
        "has the key" plus a "is it a failure" query used to cost.
        """
        if spec.stamp is None:
            return None
        try:
            return WorkerStampRepository(self.db).count_stamp_breakdown(spec)
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível ler o carimbo de '{spec.name}': {exc}")
            return None

    def _breakdown_dto(self, breakdown: StampBreakdown | None) -> WorkerStampBreakdownDTO | None:
        if breakdown is None:
            return None
        return WorkerStampBreakdownDTO(
            fingerprinted=breakdown.fingerprinted,
            legacy=breakdown.legacy,
            failed=breakdown.failed,
            unrecorded=breakdown.unrecorded,
        )

    def _processed(
        self, spec: WorkerSpec, resolved: ResolvedWorkerConfig, breakdown: StampBreakdown | None
    ) -> int | None:
        if breakdown is not None:
            return breakdown.processed
        if spec.processed_counter is None:
            return None
        try:
            return count_processed(spec, self.db, **counter_options(spec, resolved))
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível contar o processado de '{spec.name}': {exc}")
            return None

    def _failed(self, spec: WorkerSpec, resolved: ResolvedWorkerConfig, breakdown: StampBreakdown | None) -> int | None:
        if breakdown is not None:
            return breakdown.failed
        if spec.failed_counter is None:
            return None
        try:
            return count_failed(spec, self.db, **counter_options(spec, resolved))
        except Exception as exc:
            logger.error(f"⚠️ Não foi possível contar as falhas de '{spec.name}': {exc}")
            return None
