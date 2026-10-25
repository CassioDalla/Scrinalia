"""Contract of the operations panel: the workers, their configuration, the ledger and the probes.

The vocabulary the API publishes lives here rather than in the catalogue, so the contract owns what
``engine_source`` means to a client; the catalogue imports these literals instead of the schema
importing the workers.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from scrinalia.core.schemas import RequestModel
from scrinalia.domains.archive.models.enums import FailureSource, WorkerRunStatus, WorkerRunTrigger

#: Where a worker's engine/preset come from.
#:
#: ``signature`` — the worker declares ``engine_name``/``preset``, so a persisted override can
#: replace the code default. ``llm_check_rule`` — the engine is chosen by the active ``LLM_CHECK``
#: cleaning rule (the quality validator), so the panel reads the rule instead of opening a second
#: place to configure the same decision. ``none`` — the worker loads no model.
EngineSource = Literal["signature", "llm_check_rule", "none"]

#: What one unit of a worker's queue is.
WorkerUnit = Literal["staging", "document", "tag", "pair"]

#: The control an option needs. ``columns`` is a list whose values are enumerated (the columns the
#: AI text has); ``list`` is a free list of strings.
WorkerOptionKind = Literal["boolean", "integer", "number", "text", "list", "columns"]

#: Where an option is admissible: a persisted default, one execution only, or both.
WorkerOptionScope = Literal["setting", "run", "both"]


class WorkerRunDTO(BaseModel):
    """One execution of a worker, as the ledger recorded it."""

    run_id: int
    worker_name: str
    status: WorkerRunStatus
    trigger: WorkerRunTrigger
    requested_by: str | None = Field(
        default=None, description="Quem pediu a execução; nulo quando ela veio do host, sem --by."
    )
    engine_name: str | None = None
    preset: str | None = None
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuração resolvida (preset já mesclado com os overrides), para o registro não mudar de sentido quando um preset mudar no código.",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Opções efetivas do worker nesta execução (as colunas lidas, o limite de confiança), "
            "resolvidas quando a execução começou. Vazio numa linha antiga, ou numa que ainda não começou."
        ),
    )
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None
    error_fingerprint: str | None = Field(
        default=None,
        description="A causa raiz da falha, derivada da mensagem pelo PostgreSQL. Duas execuções com a mesma causa compartilham este valor.",
    )


class WorkerRunListResponse(BaseModel):
    items: list[WorkerRunDTO] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class FailureGroupDTO(BaseModel):
    """
    One root cause, with everything that happened because of it.

    ``fingerprint`` is the group's identity and the filter that leads back to the occurrences;
    ``sample`` is the most recent occurrence, because the fingerprint itself is normalized for
    grouping and reads like a key, not like a sentence. It is deliberately **not** called ``message``:
    that name is reserved for the sentence a route answers with, and ``testing/unit/api`` fails the
    build when a response carrying one forgets its ``code``. There is also deliberately **no grand
    total** across groups: they do not overlap, but adding a worker execution to an HTTP request
    would sum two different units and produce a number nobody can act on.
    """

    fingerprint: str
    sample: str = Field(description="A ocorrência mais recente, sem normalização.")
    occurrences: int = Field(ge=1)
    first_seen: datetime
    last_seen: datetime
    sources: list[FailureSource]
    worker_names: list[str] = Field(default_factory=list)
    last_path: str | None = Field(default=None, description="Rota da última falha de API do grupo.")
    last_request_id: str | None = Field(
        default=None, description="Referência da última falha de API do grupo, para achar o log."
    )


class FailureGroupListResponse(BaseModel):
    items: list[FailureGroupDTO] = Field(default_factory=list)
    total: int = Field(ge=0, description="Quantos grupos existem na janela consultada.")


class WorkerRunRequest(RequestModel):
    """Overrides for a single run; they are not persisted."""

    engine_name: str | None = None
    preset: str | None = None
    db_batch_size: int | None = Field(default=None, ge=1, le=10_000)
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="As opções declaradas pelo worker; uma chave que ele não declara é recusada.",
    )
    engine_options: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Repasse cru ao construtor do engine, para quem conhece a biblioteca. Por execução: não "
            "vira padrão. Uma chave de opção declarada aqui é recusada."
        ),
    )


class WorkerPresetDTO(BaseModel):
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class WorkerEngineDTO(BaseModel):
    name: str
    presets: list[WorkerPresetDTO] = Field(default_factory=list)


class WorkerOptionDTO(BaseModel):
    """
    One option the worker's ``execute`` declares, so the screen renders a field instead of a JSON box.

    Derived from the worker's own signature by ``workers/configuration.py``: ``kind`` is the type it
    already declares, ``default`` is its own default, and ``choices`` is the catalogue the option is
    defined against — for a column list, ``AI_TEXT_COLUMNS``, the same tuple the SQL composition and
    the benches read. The panel can therefore offer exactly what the write path accepts (#120).
    """

    name: str
    kind: WorkerOptionKind
    scope: WorkerOptionScope = Field(
        default="both",
        description="'run' é uma opção de uma execução (o cap 'limit'): não aparece no formulário de padrão.",
    )
    default: Any = None
    choices: list[str] = Field(
        default_factory=list,
        description="Os valores admitidos quando kind='columns': as colunas que o texto da IA tem.",
    )


class WorkerSettingsDTO(BaseModel):
    """
    Effective configuration of a worker, plus what can be chosen for it.

    ``overridden`` is not derived from the fields being set — a field can be ``None`` on purpose.
    It says whether a row exists, which is what lets the screen distinguish "this is the code
    default" from "somebody chose this".
    """

    worker_name: str
    engine_name: str | None = None
    preset: str | None = None
    db_batch_size: int | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    overridden: bool = False
    updated_by: str | None = None
    updated_at: datetime | None = None
    engine_source: EngineSource
    config: dict[str, Any] = Field(default_factory=dict)
    available_engines: list[WorkerEngineDTO] = Field(default_factory=list)
    declared_options: list[WorkerOptionDTO] = Field(
        default_factory=list,
        description="As opções que este worker aceita, derivadas da assinatura do execute.",
    )
    engine_option_names: list[str] = Field(
        default_factory=list,
        description=(
            "As chaves que o eixo repassa ao construtor do engine (model, device, host, ...). É a "
            "dica do bloco avançado; os valores seguem os do próprio motor."
        ),
    )
    note: str | None = None


class WorkerSettingsItemDTO(BaseModel):
    """
    One row of the configuration screen: who the worker is, and its effective configuration.

    The identity travels with the settings so the screen can be drawn from one read: the label and
    the description live in the catalogue (`workers/catalogue.py`), and asking the machine panel for
    them would make this screen pay for nine queue counts to render a heading.
    """

    name: str
    label: str
    description: str
    order: int = Field(ge=0, description="Posição na ordem do pipeline.")
    settings: WorkerSettingsDTO


class WorkerStampBreakdownDTO(BaseModel):
    """
    What the units of one worker's ledger carry, told apart by what the stamp actually says.

    One number ("processed") used to stand for all of it, and for NER that number hid the thing the
    operator needs to know: 1,650 documents carried ``"DONE"`` — a record that something ran, naming
    no producer at all. ``legacy`` is that value, plus every ``PRODUCER_UNKNOWN`` a migration left;
    ``fingerprinted`` is a value the worker's own identity pattern accepts, which really attributes
    the answer to a model. ``unrecorded`` is the key absent: nothing recorded a run.
    """

    fingerprinted: int = Field(ge=0, description="Unidades cujo carimbo nomeia o produtor.")
    legacy: int = Field(
        ge=0, description="Unidades com um carimbo que não nomeia produtor (DONE antigo ou desconhecido)."
    )
    failed: int = Field(ge=0, description="Unidades cujo carimbo registra falha.")
    unrecorded: int = Field(ge=0, description="Unidades sem carimbo algum: nada registrou uma execução.")


class WorkerStatusDTO(BaseModel):
    """One row of the panel: identity, effective configuration and the queue it addresses."""

    name: str
    label: str
    description: str
    order: int = Field(ge=0, description="Posição na ordem do pipeline.")
    unit: WorkerUnit
    governed: bool = Field(description="Se o worker respeita o bloqueio de HUMAN_APPROVED/REJECTED.")
    settings: WorkerSettingsDTO
    pending: int | None = Field(
        default=None,
        description="Unidades que a próxima execução leria. Nulo quando a fila não é mensurável barato.",
    )
    pending_reason: str | None = Field(default=None, description="Por que o pendente não é contado.")
    processed: int | None = Field(default=None, description="Unidades que o worker já carimbou.")
    failed: int | None = Field(default=None, description="Unidades cujo carimbo registra falha.")
    stamp_breakdown: WorkerStampBreakdownDTO | None = Field(
        default=None,
        description=(
            "Os quatro números do **ledger** do worker — com produtor, valor legado, falha e ausência "
            "de registro — e não da fila: `pending` é o predicado da fila, e uma unidade com carimbo "
            "de falha ou de produtor antigo conta aqui sem estar pendente. Nulo quando o ledger do "
            "worker não é um carimbo."
        ),
    )
    last_run: WorkerRunDTO | None = None
    active_run: WorkerRunDTO | None = None


class SystemWorkersResponse(BaseModel):
    """The whole panel in one request: nine workers, their configuration and their queues."""

    workers: list[WorkerStatusDTO] = Field(default_factory=list)
    generated_at: datetime


class SystemWorkerSettingsResponse(BaseModel):
    """
    The configuration screen in one request: nine workers and their persisted defaults.

    Apart from ``SystemWorkersResponse`` on purpose. Same catalogue, no queue: the panel's counters
    are the expensive half (the transfer's validates the whole staging table), and this screen shows
    none of them.
    """

    workers: list[WorkerSettingsItemDTO] = Field(default_factory=list)
    generated_at: datetime


class WorkerSettingsRequest(RequestModel):
    """A persisted default; a field left null keeps following the code."""

    engine_name: str | None = None
    preset: str | None = None
    db_batch_size: int | None = Field(default=None, ge=1, le=10_000)
    options: dict[str, Any] = Field(default_factory=dict)


class WorkerQueuePreviewDTO(BaseModel):
    """
    What a **proposed** configuration would leave in a worker's queue.

    The queue is keyed on the producer identity, so changing the engine, the preset or a declared
    option re-queues units by itself — which is the point, and also a cost the archivist has to see
    *before* saving it. Computed with the same precedence a run uses, and writing nothing.
    """

    worker_name: str
    pending: int | None = Field(default=None, description="Unidades que a execução proposta leria.")
    pending_reason: str | None = Field(default=None, description="Por que o pendente não foi contado.")


class WorkerSettingsRevisionDTO(BaseModel):
    revision_id: int
    worker_name: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    changed_by: str | None = None
    changed_at: datetime


class WorkerSettingsRevisionListResponse(BaseModel):
    items: list[WorkerSettingsRevisionDTO] = Field(default_factory=list)
    total: int = Field(ge=0)


class DatabaseHealthDTO(BaseModel):
    ok: bool
    detail: str | None = None
    documents: int | None = None
    tags: int | None = None
    entities: int | None = None
    staging_records: int | None = None


class OllamaHealthDTO(BaseModel):
    ok: bool
    host: str
    host_source: str = Field(description="De onde o host veio: OLLAMA_HOST_URL ou o default local.")
    detail: str | None = None
    installed_models: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    missing_models: list[str] = Field(default_factory=list)


class StorageHealthDTO(BaseModel):
    configured: bool
    ok: bool
    endpoint: str | None = None
    bucket: str | None = None
    detail: str | None = None


class ProcessHealthDTO(BaseModel):
    log_level: str
    debug: bool
    log_dir: str
    database: str = Field(description="host:porta/banco, sem credenciais.")
    ollama_host_url: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket_name: str | None = None
    public_scrape_configured: bool
    secrets_present: dict[str, bool] = Field(
        default_factory=dict,
        description="Presença (nunca o valor) de cada segredo configurado.",
    )


class SystemHealthResponse(BaseModel):
    """Infrastructure probes; each one answers on its own so a failure does not take the screen."""

    generated_at: datetime
    database: DatabaseHealthDTO
    ollama: OllamaHealthDTO
    storage: StorageHealthDTO
    process: ProcessHealthDTO
