"""The ingestion origin's read model, its writes and the manual entry.

This is the service behind the ingestion screen and behind the scheduler's origin branch. It owns
three things the panel needs in one answer: the origin's effective configuration, the queue the next
execution would read (through the run's own policy), and the last/active execution of that origin.
The two writes are the origin's lifecycle/agenda and one manual record.

The manual entry is deliberately **not** a shortcut to the archive. It writes the raw payload, lets
the normal staging transform structure it, and enqueues the same ``transfer`` worker the scraper
uses. The archive document is born ``PENDING_AI`` and the AI queues see it; an archivist's approval
is a later, explicit act (``PATCH /documents/{id}``), not the submit button.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.core.config import get_settings
from scrinalia.core.logger import logger
from scrinalia.domains.archive.exceptions import WorkerRunAlreadyActiveError
from scrinalia.domains.archive.models.document import ArchiveDocument
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.repository.worker_runner_repo import WorkerRunnerRepository
from scrinalia.domains.archive.schemas.responses import RouteMessageCode
from scrinalia.domains.archive.schemas.route_messages import route_message
from scrinalia.domains.archive.schemas.system_schema import WorkerRunDTO
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger
from scrinalia.domains.archive.workers.schedule import (
    InvalidCronError,
    InvalidTimezoneError,
    next_occurrence,
    validate_cron,
    validate_timezone,
)
from scrinalia.domains.ingestion import repository, worker
from scrinalia.domains.ingestion.adapters.csv import CSV_SOURCE_SCHEMA
from scrinalia.domains.ingestion.adapters.manual import MANUAL_FIELDS, MANUAL_SOURCE_SCHEMA
from scrinalia.domains.ingestion.csv_import import (
    CSV_ID_FIELD,
    CSV_TITLE_LABEL,
    MAX_CSV_BYTES,
    MAX_CSV_ROW_BYTES,
    MAX_CSV_ROWS,
    CsvRowIssue,
    CsvRowIssueCode,
    CsvRowStatus,
    payload_of,
    row_bytes,
    validate_csv_row,
)
from scrinalia.domains.ingestion.exceptions import (
    CsvImportLimitError,
    DuplicateManualRecordError,
    InvalidOriginConfigError,
    OriginDisabledError,
    OriginNotFoundError,
)
from scrinalia.domains.ingestion.models import IngestionOrigin, RawData, ScrapeStatus, ScrapingQueue
from scrinalia.domains.ingestion.origin_registry import ORIGINS, OriginSummary, get_origin_summary
from scrinalia.domains.ingestion.origin_repo import IngestionOriginRepository
from scrinalia.domains.ingestion.schemas import (
    INGESTION_OPTION_FIELDS,
    CsvImportRequest,
    CsvImportResponse,
    CsvImportResultDTO,
    CsvRowIssueDTO,
    CsvRowResultDTO,
    IngestionOriginDTO,
    IngestionOriginListResponse,
    IngestionOriginUpdateRequest,
    IngestionRunRequest,
    IngestionScheduleDTO,
    IngestionScheduleRequest,
    ManualIngestionRequest,
    ManualIngestionResponse,
    ManualIngestionResultDTO,
    OriginAvailableDTO,
    OriginConfigFieldDTO,
)
from scrinalia.domains.staging.dates import parse_document_date
from scrinalia.domains.staging.models import StagingDocument
from scrinalia.domains.staging.worker import run_staging_pipeline


def _config_of(summary: OriginSummary, origin: IngestionOrigin | None) -> dict[str, Any]:
    """The effective configuration: the model's defaults plus what the row saved."""
    raw = dict(origin.config or {}) if origin is not None else {}
    try:
        return summary.config_model.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise InvalidOriginConfigError(f"Configuração inválida da origem '{summary.code}': {exc}") from exc


def _options_of(origin: IngestionOrigin | None) -> dict[str, Any]:
    """The persisted run options, validated against the request model."""
    raw = dict(origin.options or {}) if origin is not None else {}
    try:
        return IngestionRunRequest.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise InvalidOriginConfigError(f"Opções de execução inválidas: {exc}") from exc


def _schedule_of(origin: IngestionOrigin | None) -> IngestionScheduleDTO | None:
    if origin is None or not origin.cron:
        return None
    return IngestionScheduleDTO(
        cron=origin.cron,
        timezone=origin.timezone,
        next_run_at=origin.next_run_at,
        last_enqueued_at=origin.last_enqueued_at,
        last_skipped_at=origin.last_skipped_at,
        updated_by=origin.updated_by,
        updated_at=origin.updated_at,
    )


class IngestionOriginService:
    """The ingestion screen's read model and the two writes it owns."""

    def __init__(self, db: Session, ledger: WorkerRunLedger | None = None) -> None:
        self.db = db
        self.origins = IngestionOriginRepository(db)
        self.runs = WorkerRunRepository(db)
        self.ledger = ledger or WorkerRunLedger()

    # --- reads -----------------------------------------------------------------------------------

    def list_origins(self) -> IngestionOriginListResponse:
        """
        The configured origins, with their queue and lifecycle, and the sources still to add.

        A row is the line between the two: a definition without one is **available** (the picker),
        and a definition with one is **configured**. The manual and CSV entries keep their rows for
        provenance and for the entry paths, but they are not sources: they come back with
        ``configurable=False`` so the screen shows them read-only (#206).
        """
        rows = {origin.code: origin for origin in self.origins.list_all()}
        last_runs = self.runs.last_ingestion_by_origin()
        active_runs = self.runs.active_ingestion_by_origin()
        online = [runner for runner in WorkerRunnerRepository(self.db).list_for_panel() if runner.online]
        runner_available = any("ingestion" in runner.capabilities for runner in online)

        origins = [
            self._dto(
                summary,
                rows[summary.code],
                last_runs.get(summary.code),
                active_runs.get(summary.code),
                runner_available,
            )
            for summary in ORIGINS.values()
            if summary.code in rows
        ]
        available = [
            OriginAvailableDTO(
                code=summary.code,
                label=summary.label,
                description=summary.description,
                kind=summary.kind.value,
            )
            for summary in ORIGINS.values()
            if summary.configurable and summary.code not in rows
        ]
        return IngestionOriginListResponse(
            origins=origins,
            available=available,
            generated_at=datetime.now(UTC),
        )

    def get_origin(self, code: str) -> IngestionOriginDTO:
        summary = get_origin_summary(code)
        last = self.runs.last_ingestion_by_origin().get(code)
        active = self.runs.active_ingestion_by_origin().get(code)
        online = [runner for runner in WorkerRunnerRepository(self.db).list_for_panel() if runner.online]
        return self._dto(
            summary,
            self.origins.get(code),
            last,
            active,
            any("ingestion" in runner.capabilities for runner in online),
        )

    def _dto(
        self,
        summary: OriginSummary,
        origin: IngestionOrigin | None,
        last: WorkerRunDTO | None,
        active: WorkerRunDTO | None,
        runner_available: bool,
    ) -> IngestionOriginDTO:
        options = _options_of(origin)
        pending, pending_reason = self._pending(summary.code, options)
        return IngestionOriginDTO(
            code=summary.code,
            label=summary.label,
            description=summary.description,
            kind=summary.kind.value,
            enabled=bool(origin.enabled) if origin is not None else False,
            configurable=summary.configurable,
            config=_config_of(summary, origin),
            config_fields=[
                OriginConfigFieldDTO(
                    name=field.name,
                    label=field.label,
                    help=field.help,
                    kind=field.kind,
                    required=field.required,
                    default=field.default,
                )
                for field in summary.config_fields
            ],
            options=options,
            option_fields=list(INGESTION_OPTION_FIELDS),
            schedule=_schedule_of(origin),
            pending=pending,
            pending_reason=pending_reason,
            processed=self._count(worker.count_processed, summary.code, options),
            failed=self._count(worker.count_failed, summary.code, options),
            last_run_id=last.run_id if last is not None else None,
            last_run_status=last.status if last is not None else None,
            last_run_at=(last.finished_at or last.started_at or last.queued_at) if last is not None else None,
            last_run_error=last.error if last is not None else None,
            active_run_id=active.run_id if active is not None else None,
            active_run_status=active.status if active is not None else None,
            runner_available=runner_available,
            updated_by=origin.updated_by if origin is not None else None,
            updated_at=origin.updated_at if origin is not None else None,
        )

    def _pending(self, code: str, options: dict[str, Any]) -> tuple[int | None, str | None]:
        """The queue's size through the run's own policy; a failure is a sentence, not a 500."""
        try:
            return worker.count_pending(self.db, code, **options), None
        except Exception as exc:
            logger.warning(f"Não foi possível contar a fila da origem '{code}': {exc}")
            return None, f"Não foi possível contar a fila desta origem: {exc}"

    def _count(self, fn: Any, code: str, options: dict[str, Any]) -> int | None:
        try:
            return int(fn(self.db, code, **options))
        except Exception as exc:
            logger.warning(f"Não foi possível contar o ledger da origem '{code}': {exc}")
            return None

    # --- writes ----------------------------------------------------------------------------------

    def update_origin(
        self, code: str, request: IngestionOriginUpdateRequest, *, author: Author | None = None
    ) -> IngestionOriginDTO:
        """
        Saves the lifecycle and the adapter configuration; the agenda has its own route.

        The configuration is validated by the origin's own Pydantic model, and the options by the
        run request that will consume them. A typo is a 422 with the origin's sentence, never a
        JSONB that the next run discovers at 02:00.
        """
        summary = get_origin_summary(code)
        try:
            config = summary.config_model.model_validate(request.config).model_dump(exclude_none=True)
            options = IngestionRunRequest.model_validate(request.options).model_dump(exclude_none=True)
        except ValidationError as exc:
            raise InvalidOriginConfigError(f"Configuração inválida da origem '{code}': {exc}") from exc

        origin = self.origins.upsert_settings(
            code,
            enabled=request.enabled,
            config=config,
            options=options,
            author=author,
        )
        # A paused origin has no next run; turning it back on recomputes from the same cron.
        if not request.enabled and origin.cron:
            origin.next_run_at = None
        elif request.enabled and origin.cron and origin.next_run_at is None:
            origin.next_run_at = next_occurrence(
                origin.cron, origin.timezone or get_settings().DEFAULT_TIMEZONE, datetime.now(UTC)
            )
        self.db.flush()
        return self.get_origin(code)

    def set_schedule(
        self, code: str, request: IngestionScheduleRequest, *, author: Author | None = None
    ) -> IngestionOriginDTO:
        """Validates the cron and the zone, computes the first run, and stores the agenda."""
        get_origin_summary(code)
        origin = self.origins.get(code)
        if origin is None:
            raise OriginNotFoundError(
                f"A origem '{code}' ainda não está configurada. Salve a configuração antes da agenda."
            )

        zone = request.timezone or get_settings().DEFAULT_TIMEZONE
        try:
            cron = validate_cron(request.cron)
            timezone = validate_timezone(zone)
        except InvalidCronError as exc:
            raise InvalidOriginConfigError(
                "Agenda inválida: o cron precisa de cinco campos (minuto, hora, dia do mês, mês e dia da semana)."
            ) from exc
        except InvalidTimezoneError as exc:
            raise InvalidOriginConfigError(f"Agenda inválida: '{zone}' não é um fuso IANA conhecido.") from exc

        next_run_at = next_occurrence(cron, timezone, datetime.now(UTC)) if origin.enabled else None
        self.origins.set_schedule(code, cron=cron, timezone=timezone, next_run_at=next_run_at, author=author)
        self.db.flush()
        return self.get_origin(code)

    def clear_schedule(self, code: str, *, author: Author | None = None) -> IngestionOriginDTO:
        get_origin_summary(code)
        if self.origins.get(code) is None:
            raise OriginNotFoundError(f"A origem '{code}' não está configurada.")
        self.origins.set_schedule(code, cron=None, timezone=None, next_run_at=None, author=author)
        self.db.flush()
        return self.get_origin(code)

    def trigger(self, code: str, request: IngestionRunRequest, *, requested_by: Author | None = None) -> WorkerRunDTO:
        """
        Enqueues one ingestion run for the origin, merging the persisted options with this request.

        The API only enqueues; a runner claims the row and the job resolves the origin row again. The
        ledger writes through its own committed session, so the row is visible before the response.
        """
        get_origin_summary(code)
        origin = self.origins.get(code)
        if origin is None:
            raise OriginNotFoundError(f"A origem '{code}' não está configurada.")
        if not origin.enabled:
            raise OriginDisabledError(f"A origem '{code}' está pausada; habilite-a antes de executar.")

        merged = {**_options_of(origin), **request.model_dump(exclude_none=True)}
        try:
            validated = IngestionRunRequest.model_validate(merged)
        except ValidationError as exc:
            raise InvalidOriginConfigError(f"Opções de execução inválidas: {exc}") from exc

        return self.ledger.enqueue(
            "ingestion",
            requested_by=requested_by,
            engine_name=None,
            preset=None,
            config={},
            origin_code=code,
            request={"options": validated.model_dump(exclude_none=True)},
        )

    # --- the manual origin -----------------------------------------------------------------------

    def create_manual(
        self, request: ManualIngestionRequest, *, author: Author | None = None
    ) -> ManualIngestionResponse:
        """
        Writes one typed record as the manual origin's raw payload, stages it, and queues the transfer.

        The record is not approved by being typed. It follows the same path as a scraped one; the
        transfer creates the archive description as ``PENDING_AI`` and the AI queues see it. The
        response says whether a transfer was enqueued or whether one was already in flight (in which
        case this record enters the next one), because the two are different promises.
        """
        origin = self.origins.get("manual")
        if origin is None:
            raise OriginNotFoundError("A origem manual não está configurada; rode a migração da #44.")
        if not origin.enabled:
            raise OriginDisabledError("A entrada manual está pausada; habilite a origem antes de enviar.")

        description_id = request.description_id or f"manual-{uuid4().hex}"
        if len(description_id) > 50:
            raise InvalidOriginConfigError("O identificador da entrada manual tem no máximo 50 caracteres.")
        if self.db.scalar(select(RawData.description_id).where(RawData.description_id == description_id)) is not None:
            raise DuplicateManualRecordError(f"Já existe um registro com o identificador '{description_id}'.")
        if self.db.get(ArchiveDocument, description_id) is not None:
            raise DuplicateManualRecordError(
                f"O identificador '{description_id}' já pertence a uma descrição do acervo."
            )

        payload = self._manual_payload(request)
        if not self._write_record(description_id, payload, origin_code="manual", author=author):
            raise DuplicateManualRecordError(f"Já existe um registro com o identificador '{description_id}'.")

        # The staging pipeline commits the raw record and the staged row before the transfer can be
        # claimed: a runner that saw the queued transfer first would find no staging row to move.
        run_staging_pipeline(
            self.db,
            source_schema=MANUAL_SOURCE_SCHEMA,
            origin_code="manual",
            description_id=description_id,
            limit=1,
        )

        try:
            run = self.ledger.enqueue(
                "transfer",
                requested_by=author,
                engine_name=None,
                preset=None,
                config={},
                request={},
            )
        except WorkerRunAlreadyActiveError:
            return ManualIngestionResponse(
                code=RouteMessageCode.MANUAL_INGESTION_STAGED,
                message=route_message(
                    RouteMessageCode.MANUAL_INGESTION_STAGED,
                    "Descrição recebida e estruturada. Já existe uma transferência em andamento, "
                    "então ela entra na próxima e segue para a IA depois.",
                ),
                data=ManualIngestionResultDTO(
                    description_id=description_id,
                    origin_code="manual",
                    staging_saved=True,
                    transfer_queued=False,
                    document_date=parse_document_date(request.document_date),
                    date_expression=request.document_date,
                ),
            )

        return ManualIngestionResponse(
            code=RouteMessageCode.MANUAL_INGESTION_QUEUED,
            message=route_message(
                RouteMessageCode.MANUAL_INGESTION_QUEUED,
                "Descrição recebida e estruturada. A transferência foi enfileirada; a IA vai "
                "enriquecê-la e o registro continua em revisão.",
            ),
            data=ManualIngestionResultDTO(
                description_id=description_id,
                origin_code="manual",
                staging_saved=True,
                transfer_run_id=run.run_id,
                transfer_queued=True,
                document_date=parse_document_date(request.document_date),
                date_expression=request.document_date,
            ),
        )

    @staticmethod
    def _manual_payload(request: ManualIngestionRequest) -> dict[str, Any]:
        """
        The manual origin's payload: the form fields, with the date exactly as the archivist wrote it.

        The date is **not** converted to ISO here: the staging transform parses it with the language
        profile and keeps the spelling in ``date_expression``, which is the whole point of accepting
        ``Década de 1980`` from a person. Converting it here would parse the same value twice and
        lose the expression.
        """
        payload: dict[str, Any] = {"title": request.title}
        if request.document_date:
            payload["document_date"] = request.document_date
        for field in MANUAL_FIELDS:
            value = getattr(request, field, None)
            if value is not None and value != "":
                payload[field] = value
        return payload

    # --- the CSV origin -------------------------------------------------------------------------

    def import_csv(self, request: CsvImportRequest, *, author: Author | None = None) -> CsvImportResponse:
        """
        Writes a bounded list of rows as the CSV origin's raw payload, stages the accepted ones,
        and queues one transfer for the batch.

        The rows are the file parsed in the browser: nothing is uploaded and nothing is persisted
        as a file (#191). Each row is validated with the staging model, written only when it is
        valid and its id is new, and reported back as accepted, duplicated or invalid. A partial
        import is normal — the rejected rows stay out, the accepted ones follow the same path as a
        scraped record, and the archive description is born ``PENDING_AI``.
        """
        origin = self.origins.get("csv")
        if origin is None:
            raise OriginNotFoundError("A origem CSV não está configurada; rode a migração da #191.")
        if not origin.enabled:
            raise OriginDisabledError("A importação CSV está pausada; habilite a origem antes de enviar.")

        received = len(request.rows)
        if received > MAX_CSV_ROWS:
            raise CsvImportLimitError(
                f"A importação aceita no máximo {MAX_CSV_ROWS} linhas por vez; o arquivo tem {received}."
            )
        total_bytes = sum(row_bytes(row.fields) for row in request.rows)
        if total_bytes > MAX_CSV_BYTES:
            limit_mb = MAX_CSV_BYTES // (1024 * 1024)
            raise CsvImportLimitError(
                f"A importação tem {total_bytes / (1024 * 1024):.1f} MB; o limite é {limit_mb} MB. "
                "Divida o arquivo em partes."
            )

        existing = self._existing_ids([row.description_id.strip() for row in request.rows])
        seen: set[str] = set()
        results: list[CsvRowResultDTO] = []
        accepted: list[str] = []

        for index, row in enumerate(request.rows, start=2):
            identifier = row.description_id.strip()
            line = row.line or index
            row_size = row_bytes(row.fields)
            issues: list[CsvRowIssue]
            if row_size > MAX_CSV_ROW_BYTES:
                issues = [
                    CsvRowIssue(
                        field=None,
                        code=CsvRowIssueCode.ROW_TOO_LARGE,
                        message=(
                            f"A linha tem {max(1, row_size // 1024)} KB; o limite por linha é "
                            f"{MAX_CSV_ROW_BYTES // 1024} KB."
                        ),
                    )
                ]
            else:
                issues = validate_csv_row(identifier, row.fields)

            if not issues:
                if identifier in existing:
                    issues = [
                        CsvRowIssue(
                            field=CSV_ID_FIELD.label,
                            code=CsvRowIssueCode.ALREADY_EXISTS,
                            message=f"Já existe um registro com o identificador '{identifier}'.",
                        )
                    ]
                elif identifier in seen:
                    issues = [
                        CsvRowIssue(
                            field=CSV_ID_FIELD.label,
                            code=CsvRowIssueCode.DUPLICATE_IN_BATCH,
                            message=f"O identificador '{identifier}' repete uma linha anterior deste arquivo.",
                        )
                    ]

            if issues:
                duplicated = all(
                    issue.code in (CsvRowIssueCode.ALREADY_EXISTS, CsvRowIssueCode.DUPLICATE_IN_BATCH)
                    for issue in issues
                )
                results.append(
                    self._csv_row_result(
                        line,
                        identifier,
                        CsvRowStatus.DUPLICATED if duplicated else CsvRowStatus.INVALID,
                        issues,
                    )
                )
                continue

            payload = payload_of(row.fields)
            raw_title = payload.get(CSV_TITLE_LABEL)
            if not self._write_record(identifier, payload, origin_code="csv", author=author, raw_title=raw_title):
                results.append(
                    self._csv_row_result(
                        line,
                        identifier,
                        CsvRowStatus.DUPLICATED,
                        [
                            CsvRowIssue(
                                field=CSV_ID_FIELD.label,
                                code=CsvRowIssueCode.ALREADY_EXISTS,
                                message=f"Já existe um registro com o identificador '{identifier}'.",
                            )
                        ],
                    )
                )
                continue

            seen.add(identifier)
            accepted.append(identifier)
            results.append(self._csv_row_result(line, identifier, CsvRowStatus.ACCEPTED, []))

        if accepted:
            # One staging run for exactly the rows just written: leftovers of an earlier import are
            # not staged in their place, and the batch is committed before the transfer is queued.
            run_staging_pipeline(
                self.db,
                source_schema=CSV_SOURCE_SCHEMA,
                origin_code="csv",
                description_ids=accepted,
            )
            staged = set(
                self.db.scalars(
                    select(StagingDocument.description_id).where(StagingDocument.description_id.in_(accepted))
                )
            )
            not_staged = set(accepted) - staged
            if not_staged:
                for result in results:
                    if result.status is CsvRowStatus.ACCEPTED and result.description_id in not_staged:
                        result.status = CsvRowStatus.INVALID
                        result.issues = [
                            CsvRowIssueDTO(
                                field=None,
                                code=CsvRowIssueCode.STAGING_FAILED,
                                message=(
                                    "O registro não pôde ser estruturado; ele ficou na fila e a próxima "
                                    "execução o tenta de novo."
                                ),
                            )
                        ]
                accepted = [identifier for identifier in accepted if identifier in staged]

        transfer_run_id: int | None = None
        transfer_queued = False
        if accepted:
            try:
                run = self.ledger.enqueue(
                    "transfer",
                    requested_by=author,
                    engine_name=None,
                    preset=None,
                    config={},
                    request={},
                )
            except WorkerRunAlreadyActiveError:
                transfer_queued = False
            else:
                transfer_run_id = run.run_id
                transfer_queued = True

        duplicated_count = sum(1 for result in results if result.status is CsvRowStatus.DUPLICATED)
        invalid_count = sum(1 for result in results if result.status is CsvRowStatus.INVALID)
        code, message = self._csv_message(
            accepted=len(accepted),
            received=received,
            duplicated=duplicated_count,
            invalid=invalid_count,
            transfer_queued=transfer_queued,
        )
        return CsvImportResponse(
            code=code,
            message=message,
            data=CsvImportResultDTO(
                origin_code="csv",
                received=received,
                accepted=len(accepted),
                duplicated=duplicated_count,
                invalid=invalid_count,
                rows=results,
                transfer_run_id=transfer_run_id,
                transfer_queued=transfer_queued,
            ),
        )

    def _existing_ids(self, description_ids: Sequence[str]) -> set[str]:
        """The ids the three layers already know: a row reusing one is duplicated, not overwritten."""
        wanted = [identifier for identifier in description_ids if identifier]
        if not wanted:
            return set()
        existing = set(self.db.scalars(select(RawData.description_id).where(RawData.description_id.in_(wanted))))
        existing.update(
            self.db.scalars(select(ScrapingQueue.description_id).where(ScrapingQueue.description_id.in_(wanted)))
        )
        existing.update(
            self.db.scalars(select(ArchiveDocument.description_id).where(ArchiveDocument.description_id.in_(wanted)))
        )
        return existing

    def _write_record(
        self,
        description_id: str,
        payload: dict[str, Any],
        *,
        origin_code: str,
        author: Author | None = None,
        raw_title: str | None = None,
    ) -> bool:
        """
        The raw payload and the ``DONE`` queue row, in one savepoint.

        Both writes belong together: a queue row without a payload would look discovered but never
        scraped, and a payload without a queue row would be staged without the discovery record.
        A duplicate id rolls the savepoint back and returns ``False``; the caller decides whether
        that is a refusal (the manual form) or a per-row result (the CSV import).
        """
        savepoint = self.db.begin_nested()
        try:
            repository.save_raw_data(
                self.db,
                description_id,
                payload,
                origin_code=origin_code,
                author=author,
                raw_title=raw_title,
            )
            if repository.add(self.db, description_id, origin_code=origin_code) is None:
                savepoint.rollback()
                return False
            repository.update_queue_status(self.db, description_id, ScrapeStatus.DONE, origin_code=origin_code)
        except Exception:
            savepoint.rollback()
            raise
        savepoint.commit()
        return True

    @staticmethod
    def _csv_row_result(
        line: int,
        description_id: str,
        status: CsvRowStatus,
        issues: list[CsvRowIssue],
    ) -> CsvRowResultDTO:
        """One row's report, from the domain's issue objects to the contract's DTOs."""
        return CsvRowResultDTO(
            line=line,
            description_id=description_id,
            status=status,
            issues=[CsvRowIssueDTO(field=issue.field, code=issue.code, message=issue.message) for issue in issues],
        )

    @staticmethod
    def _csv_message(
        *,
        accepted: int,
        received: int,
        duplicated: int,
        invalid: int,
        transfer_queued: bool,
    ) -> tuple[RouteMessageCode, str]:
        """The batch's sentence and the code that identifies the outcome, not the wording."""
        if accepted == 0:
            return (
                RouteMessageCode.CSV_IMPORT_REFUSED,
                route_message(
                    RouteMessageCode.CSV_IMPORT_REFUSED,
                    "Nenhuma das {received} linhas entrou: {duplicated} duplicadas e {invalid} inválidas. "
                    "Corrija a prévia e envie de novo.",
                    received=received,
                    duplicated=duplicated,
                    invalid=invalid,
                ),
            )
        if transfer_queued:
            return (
                RouteMessageCode.CSV_IMPORT_QUEUED,
                route_message(
                    RouteMessageCode.CSV_IMPORT_QUEUED,
                    "{accepted} de {received} linhas importadas ({duplicated} duplicadas, {invalid} inválidas). "
                    "A transferência foi enfileirada; a IA vai enriquecê-las e elas continuam em revisão.",
                    accepted=accepted,
                    received=received,
                    duplicated=duplicated,
                    invalid=invalid,
                ),
            )
        return (
            RouteMessageCode.CSV_IMPORT_STAGED,
            route_message(
                RouteMessageCode.CSV_IMPORT_STAGED,
                "{accepted} de {received} linhas importadas ({duplicated} duplicadas, {invalid} inválidas). "
                "Já existe uma transferência em andamento, então elas entram na próxima e seguem para a IA depois.",
                accepted=accepted,
                received=received,
                duplicated=duplicated,
                invalid=invalid,
            ),
        )
