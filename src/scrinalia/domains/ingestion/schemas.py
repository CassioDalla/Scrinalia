"""Contract of the ingestion surface: origins, their agenda and the manual entry.

The origin is an operational object, so its screen needs more than a name: the configuration fields
it can edit, the run options a scheduled execution inherits, the queue it addresses and the run it
last executed. The DTOs below are that read model plus the two writes (configuration and agenda) and
the manual body.

The manual body is a `RequestModel` (``extra="forbid"``) like every other write: a field the API does
not read is a 400 and not a silent drop, and the form's own copy of the list is derived from the
generated client.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from scrinalia.core.language import get_language
from scrinalia.core.schemas import RequestModel
from scrinalia.domains.archive.models.enums import WorkerRunStatus
from scrinalia.domains.archive.schemas.responses import RouteResponse
from scrinalia.domains.ingestion.csv_import import (
    CSV_FIELDS,
    CSV_ID_FIELD,
    MAX_CSV_BYTES,
    MAX_CSV_FIELD_CHARS,
    MAX_CSV_ROW_BYTES,
    MAX_CSV_ROWS,
    CsvField,
    CsvFieldKind,
    CsvRowIssueCode,
    CsvRowStatus,
)
from scrinalia.domains.staging.dates import parse_document_date

#: The control a configuration field needs on the screen.
ConfigFieldKind = Literal["text", "number", "boolean"]

#: The control a run option needs. The ingestion options are numbers, booleans and nothing else.
OptionKind = Literal["boolean", "integer", "number", "text"]


class OriginConfigFieldDTO(RequestModel):
    """One editable field of an origin's configuration, with its label and help."""

    name: str
    label: str
    help: str
    kind: ConfigFieldKind = "text"
    required: bool = False
    default: Any = None


class IngestionOptionDTO(RequestModel):
    """One run option the scheduler and the run dialog can carry."""

    name: str
    label: str
    help: str
    kind: OptionKind = "integer"
    default: Any = None


class IngestionScheduleDTO(RequestModel):
    """The origin's agenda, as the screen reads it; ``next_run_at`` is null while paused."""

    cron: str | None = None
    timezone: str | None = None
    next_run_at: datetime | None = None
    last_enqueued_at: datetime | None = None
    last_skipped_at: datetime | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class IngestionOriginDTO(RequestModel):
    """
    One origin as the ingestion screen sees it.

    ``pending`` is counted through the same policy the next execution uses (the scraper's queue
    window, or the manual origin's unstaged raw records); ``processed``/``failed`` are the ledger
    numbers of that origin, never a collection-wide total. ``last_run``/``active_run`` are flattened
    so this contract does not have to import the run DTO, and the full ledger stays on
    ``/system/runs?origin=...``.
    """

    code: str
    label: str
    description: str
    kind: str
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    config_fields: list[OriginConfigFieldDTO] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    option_fields: list[IngestionOptionDTO] = Field(default_factory=list)
    schedule: IngestionScheduleDTO | None = None
    pending: int | None = Field(default=None, description="O que a próxima execução desta origem leria.")
    pending_reason: str | None = None
    processed: int | None = None
    failed: int | None = None
    last_run_id: int | None = None
    last_run_status: WorkerRunStatus | None = None
    last_run_at: datetime | None = None
    last_run_error: str | None = None
    active_run_id: int | None = None
    active_run_status: WorkerRunStatus | None = None
    runner_available: bool = Field(
        default=False,
        description="Se algum runner online aceita a etapa de ingestão; falso não impede enfileirar.",
    )
    updated_by: str | None = None
    updated_at: datetime | None = None


class IngestionOriginListResponse(RequestModel):
    origins: list[IngestionOriginDTO] = Field(default_factory=list)
    generated_at: datetime


class IngestionOriginUpdateRequest(RequestModel):
    """The origin's lifecycle and configuration; the agenda has its own route."""

    enabled: bool
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="A configuração do adapter, validada pelo modelo da origem (URLs, espera).",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="O padrão de execução agendada (páginas, janelas, retentativas).",
    )


class IngestionScheduleRequest(RequestModel):
    """The agenda: a five-field cron and an IANA zone. The origin's ``enabled`` is its own field."""

    cron: str = Field(min_length=1, max_length=120, description="Cinco campos: minuto, hora, dia, mês, semana.")
    timezone: str | None = Field(default=None, max_length=64, description="Zona IANA; o padrão é DEFAULT_TIMEZONE.")


class IngestionRunRequest(RequestModel):
    """
    The options of one ingestion execution; the persisted origin options are the defaults.

    ``pages`` defaults to one listing page, because a scheduled crawl that walked to the end of the
    site would never finish inside its slot. ``limit`` is the batch cap; the manual origin ignores
    the scrape options and stages the records it can.
    """

    pages: int | None = Field(default=None, ge=0, description="Páginas da listagem; 0 não lista.")
    limit: int | None = Field(default=None, ge=1, description="Máximo de registros desta execução.")
    audit_ttl_days: int | None = Field(default=None, ge=1, description="Re-lê os DONE com mais de N dias.")
    force_retry_fatal: bool = Field(default=False, description="Inclui os registros marcados FATAL_ERROR.")
    ignore_sliding_window: bool = Field(default=False, description="Ignora as janelas de descoberta e TTL.")
    max_retries: int | None = Field(default=None, ge=0, description="Falhas transitórias antes de FATAL.")
    discovery_window_days: int | None = Field(
        default=None, ge=1, description="Só registros descobertos nos últimos N dias."
    )
    scraped_ttl_days: int | None = Field(default=None, ge=1, description="Só registros lidos há mais de N dias.")


#: The labels and help of the run options. They are presentation, and the test beside the model
#: pins that every field of ``IngestionRunRequest`` has exactly one entry here.
INGESTION_OPTION_FIELDS: tuple[IngestionOptionDTO, ...] = (
    IngestionOptionDTO(
        name="pages",
        label="Páginas da listagem",
        help="Quantas páginas de listagem a execução percorre; 0 não lista.",
        kind="integer",
        default=1,
    ),
    IngestionOptionDTO(
        name="limit",
        label="Limite de registros",
        help="Máximo de registros que esta execução toma da fila.",
        kind="integer",
    ),
    IngestionOptionDTO(
        name="audit_ttl_days",
        label="Auditoria (dias)",
        help="Re-lê os registros concluídos há mais de N dias.",
        kind="integer",
    ),
    IngestionOptionDTO(
        name="force_retry_fatal",
        label="Incluir falhas permanentes",
        help="Toma também os registros marcados FATAL_ERROR.",
        kind="boolean",
        default=False,
    ),
    IngestionOptionDTO(
        name="ignore_sliding_window",
        label="Ignorar janelas",
        help="Ignora as janelas de descoberta e TTL e toma tudo o que os status permitem.",
        kind="boolean",
        default=False,
    ),
    IngestionOptionDTO(
        name="max_retries",
        label="Tentativas transitórias",
        help="Falhas de rede antes de marcar FATAL_ERROR.",
        kind="integer",
    ),
    IngestionOptionDTO(
        name="discovery_window_days",
        label="Janela de descoberta (dias)",
        help="Só considera registros descobertos nos últimos N dias.",
        kind="integer",
    ),
    IngestionOptionDTO(
        name="scraped_ttl_days",
        label="TTL da leitura (dias)",
        help="Só considera registros lidos há mais de N dias.",
        kind="integer",
    ),
)


class ManualIngestionRequest(RequestModel):
    """
    One record typed by an archivist: the whole ISAD(G) record the archive stores.

    It is the **manual origin's payload**, not an approval: the record goes through the same staging,
    the same transfer and the same AI queues as a scraped one. ``title`` is the only required field —
    an archivist may not know the date or the producer yet, and a description is allowed to be
    incomplete while it is being made.

    ``document_date`` is **text**, not a ``date``: the archivist types what the record says
    (``Década de 1980``, ``1951-1953``) and the language profile parses it, which is exactly what the
    CSV import already does. A value the profile cannot read is refused here with a sentence, instead
    of becoming ``None`` in the staging transform. The two entrances then share one grammar.

    ``description_dates`` is deliberately absent: the archive knows when the description was made and
    the revision ledger records every edit, so asking for it invites a contradiction. ``attachment_link``
    is absent too — nothing reads it, and the digital object is #198.
    """

    #: The client generates it (``manual-<uuid>``) so a retried submit is the same record. Omitted,
    #: the API generates one; a duplicate answers 409.
    description_id: str | None = Field(default=None, max_length=50, description="Identificador do registro.")
    title: str = Field(min_length=1, max_length=500, description="Título da descrição.")
    document_date: str | None = Field(
        default=None,
        max_length=MAX_CSV_FIELD_CHARS,
        description="Data de produção como está na fonte: AAAA-MM-DD, década ou intervalo.",
    )
    reference_code: str | None = Field(default=None, max_length=500, description="Código de referência.")
    level: str | None = Field(default=None, max_length=200, description="Nível de descrição.")
    parent_reference_code: str | None = Field(default=None, max_length=500, description="Código da unidade superior.")
    dimension_support: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Dimensão e suporte."
    )
    producers: str | None = Field(default=None, max_length=MAX_CSV_FIELD_CHARS, description="Produtores.")
    admin_bio_history: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="História administrativa/biográfica."
    )
    admin_archival_history: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="História arquivística."
    )
    provenance: str | None = Field(default=None, max_length=MAX_CSV_FIELD_CHARS, description="Procedência.")
    scope_content: str | None = Field(default=None, max_length=MAX_CSV_FIELD_CHARS, description="Âmbito e conteúdo.")
    appraisal_destruction: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Avaliação e temporalidade."
    )
    accruals: str | None = Field(default=None, max_length=MAX_CSV_FIELD_CHARS, description="Incorporações.")
    arrangement: str | None = Field(default=None, max_length=MAX_CSV_FIELD_CHARS, description="Sistema de arranjo.")
    access_conditions: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Condições de acesso."
    )
    reproduction_conditions: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Condições de reprodução."
    )
    language_name: str | None = Field(default=None, max_length=MAX_CSV_FIELD_CHARS, description="Idioma.")
    physical_characteristics: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Características físicas."
    )
    finding_aids: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Instrumentos de pesquisa."
    )
    originals_location: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Localização dos originais."
    )
    copies_location: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Localização das cópias."
    )
    related_units: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Unidades de descrição relacionadas."
    )
    publication_notes: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Notas de publicação."
    )
    conservation_notes: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Notas de conservação."
    )
    general_notes: str | None = Field(default=None, max_length=MAX_CSV_FIELD_CHARS, description="Notas gerais.")
    archivist_notes: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Notas do arquivista."
    )
    rules_conventions: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Regras ou convenções."
    )
    indexing_points: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="Pontos de acesso, separados por vírgula."
    )
    original_url: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="URL da página de onde o registro veio."
    )
    thumb_down_link: str | None = Field(
        default=None, max_length=MAX_CSV_FIELD_CHARS, description="URL da imagem que o worker de miniatura baixa."
    )

    @field_validator("document_date")
    @classmethod
    def _the_language_has_to_read_the_date(cls, value: str | None) -> str | None:
        """
        A date the profile cannot read is a sentence, not a silent ``None``.

        The staging transform is deliberately forgiving (an unreadable date becomes ``None``) because
        a scraped record must not be lost over its date. A person typing a record is the opposite
        case: they can fix it now, and the CSV import already refuses the row for the same reason.
        """
        if value is None:
            return None
        text = " ".join(value.split())
        if not text or text.lower() in get_language().empty_date_values:
            return None
        if parse_document_date(text) is None:
            raise ValueError(f"A data '{text[:40]}' não foi reconhecida. Use AAAA-MM-DD, uma década ou um intervalo.")
        return text


class ManualIngestionResultDTO(RequestModel):
    """What the submit created and what happened to the transfer that follows it."""

    description_id: str
    origin_code: str
    staging_saved: bool
    transfer_run_id: int | None = Field(
        default=None, description="A execução de transferência enfileirada; nula quando já havia uma ativa."
    )
    transfer_queued: bool = Field(
        default=False, description="Falso quando uma transferência já estava em andamento e esta entra na próxima."
    )
    review_status: str = Field(
        default="PENDING_AI",
        description="O estado inicial no archive: a ingestão manual não marca HUMAN_APPROVED.",
    )
    document_date: date | None = Field(
        default=None,
        description="A data que o perfil de idioma leu do texto, para a confirmação mostrar o que foi gravado.",
    )
    date_expression: str | None = Field(
        default=None, description="A data como o arquivista a escreveu, quando havia uma."
    )


class ManualIngestionResponse(RouteResponse):
    """The submit's sentence and the record it produced."""

    data: ManualIngestionResultDTO


# ==========================================
# THE CSV IMPORT
# ==========================================


class CsvFieldDTO(RequestModel):
    """
    One column of the CSV import, as the screen and the template render it.

    ``label`` is the file's header and the key the payload carries; ``attribute`` is the staging
    column it fills. The pair is metadata about the origin's own ``SourceSchema``, not a second
    map: the route validates the row against the same catalogue the schema was built from.
    """

    label: str
    attribute: str
    help: str
    kind: CsvFieldKind = "text"
    required: bool = False
    max_length: int | None = None


class CsvImportSpecResponse(RequestModel):
    """Everything the screen needs to parse and validate a file before sending it."""

    origin_code: str
    #: The record's identity column, which is outside the staging payload.
    id: CsvFieldDTO
    fields: list[CsvFieldDTO] = Field(default_factory=list)
    max_rows: int
    max_bytes: int
    max_row_bytes: int
    max_field_chars: int


class CsvImportRow(RequestModel):
    """One row of the file: its identity, the line for the screen, and its cells by label."""

    #: 1-based line in the file, header included; ``0`` when the client did not send one.
    line: int = Field(default=0, ge=0, description="A linha do arquivo, para a tela.")
    description_id: str = Field(description="Identificador único do registro.")
    fields: dict[str, str] = Field(
        default_factory=dict,
        description="As células da linha, com o rótulo do mapa como chave.",
    )


class CsvImportRequest(RequestModel):
    """A bounded list of rows, never a file: the CSV is parsed in the browser (issue #191)."""

    rows: list[CsvImportRow] = Field(
        min_length=1,
    )


class CsvRowIssueDTO(RequestModel):
    """Why one row did not enter, with the label the person sees and a Portuguese sentence."""

    field: str | None = None
    code: CsvRowIssueCode
    message: str


class CsvRowResultDTO(RequestModel):
    """What happened to one row: accepted, duplicated or invalid, and why."""

    line: int
    description_id: str
    status: CsvRowStatus
    issues: list[CsvRowIssueDTO] = Field(default_factory=list)


class CsvImportResultDTO(RequestModel):
    """The batch's per-row report and what happened to the transfer that follows it."""

    origin_code: str
    received: int
    accepted: int
    duplicated: int
    invalid: int
    rows: list[CsvRowResultDTO] = Field(default_factory=list)
    transfer_run_id: int | None = None
    transfer_queued: bool = False
    review_status: str = Field(
        default="PENDING_AI",
        description="O estado inicial no archive: a importação não marca HUMAN_APPROVED.",
    )


class CsvImportResponse(RouteResponse):
    """The import's sentence and its per-row report."""

    data: CsvImportResultDTO


def _csv_field_dto(field: CsvField) -> CsvFieldDTO:
    """Presents one catalogue entry as the contract's field."""
    return CsvFieldDTO(
        label=field.label,
        attribute=field.attribute,
        help=field.help,
        kind=field.kind,
        required=field.required,
        max_length=field.max_length,
    )


def build_csv_import_spec() -> CsvImportSpecResponse:
    """The map and the bounds, derived from their one definition (``csv_import``)."""
    return CsvImportSpecResponse(
        origin_code="csv",
        id=_csv_field_dto(CSV_ID_FIELD),
        fields=[_csv_field_dto(field) for field in CSV_FIELDS],
        max_rows=MAX_CSV_ROWS,
        max_bytes=MAX_CSV_BYTES,
        max_row_bytes=MAX_CSV_ROW_BYTES,
        max_field_chars=MAX_CSV_FIELD_CHARS,
    )
