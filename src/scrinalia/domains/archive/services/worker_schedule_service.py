"""The worker agenda: the panel's read and write of one cron row (ADR 0015).

The service validates what the scheduler will later trust: the five-field cron, the IANA zone and the
pinned request against the worker's catalogue. The ``next_run_at`` is computed here, at save time, so
the panel can show when the schedule will first run; the scheduler recomputes it from the same helper
on every tick, so the two cannot drift into two cron implementations.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.core.config import get_settings
from scrinalia.core.i18n import t
from scrinalia.domains.archive.exceptions import (
    InvalidWorkerScheduleError,
    InvalidWorkerSettingsError,
    WorkerNotFoundError,
    WorkerScheduleNotFoundError,
)
from scrinalia.domains.archive.models.operations import WorkerSchedule
from scrinalia.domains.archive.repository.worker_schedule_repo import WorkerScheduleRepository
from scrinalia.domains.archive.schemas.system_schema import (
    WorkerRunRequest,
    WorkerScheduleDTO,
    WorkerScheduleRequest,
)
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE
from scrinalia.domains.archive.workers.configuration import (
    validate_engine_choice,
    validate_engine_options,
    validate_options,
)
from scrinalia.domains.archive.workers.schedule import (
    InvalidCronError,
    InvalidTimezoneError,
    next_occurrence,
    validate_cron,
    validate_timezone,
)


def to_schedule_dto(schedule: WorkerSchedule) -> WorkerScheduleDTO:
    """Maps the row to the contract shape; the stored request is the validated body."""
    return WorkerScheduleDTO(
        worker_name=schedule.worker_name,
        enabled=schedule.enabled,
        cron=schedule.cron,
        timezone=schedule.timezone,
        request=WorkerRunRequest.model_validate(schedule.request or {}),
        next_run_at=schedule.next_run_at,
        last_enqueued_at=schedule.last_enqueued_at,
        last_skipped_at=schedule.last_skipped_at,
        updated_by=schedule.updated_by,
        updated_at=schedule.updated_at,
    )


class WorkerScheduleService:
    """Reads and writes the agenda over the request transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.schedules = WorkerScheduleRepository(db)

    def get(self, worker_name: str) -> WorkerScheduleDTO | None:
        """The worker's agenda, or ``None`` when it has none."""
        self._spec(worker_name)
        schedule = self.schedules.get(worker_name)
        return to_schedule_dto(schedule) if schedule is not None else None

    def upsert(
        self, worker_name: str, data: WorkerScheduleRequest, *, author: Author | None = None
    ) -> WorkerScheduleDTO:
        """
        Validates the cron, the zone and the request, and creates or replaces the agenda.

        A disabled schedule stores ``next_run_at = NULL``: the pause has to be a state the scheduler
        cannot mistake for "due", and turning it back on recomputes the next occurrence from the cron.
        """
        spec = self._spec(worker_name)
        zona = data.timezone or get_settings().DEFAULT_TIMEZONE
        try:
            cron = validate_cron(data.cron)
            timezone = validate_timezone(zona)
        except InvalidCronError as exc:
            raise InvalidWorkerScheduleError(
                t("Agenda inválida: o cron precisa de cinco campos (minuto, hora, dia do mês, mês e dia da semana).")
            ) from exc
        except InvalidTimezoneError as exc:
            raise InvalidWorkerScheduleError(
                t("Agenda inválida: '{zona}' não é um fuso IANA conhecido.", zona=zona)
            ) from exc

        validate_engine_choice(spec, data.request.engine_name, data.request.preset)
        validate_options(spec, data.request.options)
        validate_engine_options(spec, data.request.engine_options)

        next_run_at = next_occurrence(cron, timezone, datetime.now(UTC)) if data.enabled else None
        schedule = self.schedules.upsert(
            worker_name,
            enabled=data.enabled,
            cron=cron,
            timezone=timezone,
            request=data.request.model_dump(mode="json"),
            next_run_at=next_run_at,
            author=author,
        )
        self.db.commit()
        return to_schedule_dto(schedule)

    def delete(self, worker_name: str) -> None:
        """Removes the agenda; the runs it already created stay in the ledger."""
        self._spec(worker_name)
        if not self.schedules.delete(worker_name):
            raise WorkerScheduleNotFoundError(t("O worker '{worker_name}' não tem agenda.", worker_name=worker_name))
        self.db.commit()

    def _spec(self, worker_name: str):
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
                t("A agenda da ingestão é a da origem: use a tela de ingestão, não a agenda genérica de workers.")
            )
        return spec
