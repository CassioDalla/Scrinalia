"""Contract of the operations panel: the workers, their configuration, the ledger and the probes.

The vocabulary the API publishes lives here rather than in the catalogue, so the contract owns what
``engine_source`` means to a client; the catalogue imports these literals instead of the schema
importing the workers.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from memoria_curitibana.domains.archive.models.enums import WorkerRunStatus, WorkerRunTrigger

#: Where a worker's engine/preset come from.
#:
#: ``signature`` — the worker declares ``engine_name``/``preset``, so a persisted override can
#: replace the code default. ``llm_check_rule`` — the engine is chosen by the active ``LLM_CHECK``
#: cleaning rule (the quality validator), so the panel reads the rule instead of opening a second
#: place to configure the same decision. ``none`` — the worker loads no model.
EngineSource = Literal["signature", "llm_check_rule", "none"]

#: What one unit of a worker's queue is.
WorkerUnit = Literal["staging", "document", "tag", "pair"]


class WorkerRunDTO(BaseModel):
    """One execution of a worker, as the ledger recorded it."""

    run_id: int
    worker_name: str
    status: WorkerRunStatus
    trigger: WorkerRunTrigger
    requested_by: str | None = Field(default=None, description="Quem pediu a execução; texto livre até haver auth.")
    engine_name: str | None = None
    preset: str | None = None
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuração resolvida (preset já mesclado com os overrides), para o registro não mudar de sentido quando um preset mudar no código.",
    )
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None


class WorkerRunListResponse(BaseModel):
    items: list[WorkerRunDTO] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class WorkerRunRequest(BaseModel):
    """Overrides for a single run; they are not persisted."""

    engine_name: str | None = None
    preset: str | None = None
    db_batch_size: int | None = Field(default=None, ge=1, le=10_000)
    options: dict[str, Any] = Field(default_factory=dict)
    requested_by: str | None = None


class WorkerPresetDTO(BaseModel):
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class WorkerEngineDTO(BaseModel):
    name: str
    presets: list[WorkerPresetDTO] = Field(default_factory=list)


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
    note: str | None = None


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
    last_run: WorkerRunDTO | None = None
    active_run: WorkerRunDTO | None = None


class SystemWorkersResponse(BaseModel):
    """The whole panel in one request: nine workers, their configuration and their queues."""

    workers: list[WorkerStatusDTO] = Field(default_factory=list)
    generated_at: datetime


class WorkerSettingsRequest(BaseModel):
    """A persisted default; a field left null keeps following the code."""

    engine_name: str | None = None
    preset: str | None = None
    db_batch_size: int | None = Field(default=None, ge=1, le=10_000)
    options: dict[str, Any] = Field(default_factory=dict)
    changed_by: str | None = None


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
    arqdoc_configured: bool
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
