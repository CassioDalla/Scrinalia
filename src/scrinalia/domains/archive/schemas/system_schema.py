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
from scrinalia.domains.archive.schemas.responses import RouteResponse

#: Where a worker's engine/preset come from.
#:
#: ``signature`` — the worker declares ``engine_name``/``preset``, so a persisted override can
#: replace the code default. ``llm_check_rule`` — the engine is chosen by the active ``LLM_CHECK``
#: cleaning rule (the quality validator), so the panel reads the rule instead of opening a second
#: place to configure the same decision. ``none`` — the worker loads no model.
EngineSource = Literal["signature", "llm_check_rule", "none"]

#: What one unit of a worker's queue is.
WorkerUnit = Literal["origin", "channel", "staging", "document", "tag", "pair"]

#: The control an option needs. ``columns`` is a list whose values are enumerated (the columns the
#: AI text has); ``list`` is a free list of strings.
WorkerOptionKind = Literal["boolean", "integer", "number", "text", "list", "columns"]

#: Where an option is admissible: a persisted default, one execution only, or both.
WorkerOptionScope = Literal["setting", "run", "both"]


class WorkerRunDTO(BaseModel):
    """One execution of a worker, as the ledger recorded it."""

    run_id: int
    worker_name: str
    origin_code: str | None = Field(
        default=None,
        description=(
            "A origem que esta execução de ingestão processou; nula num worker de archive, que "
            "atravessa o acervo inteiro e não tem uma única origem para nomear."
        ),
    )
    channel_code: str | None = Field(
        default=None,
        description=(
            "O canal de difusão que esta execução de exportação escreveu; nulo em qualquer outro "
            "worker, inclusive na ingestão, cujo eixo é a origem (ADR 0023)."
        ),
    )
    status: WorkerRunStatus
    trigger: WorkerRunTrigger
    trial: bool = Field(
        default=False,
        description=(
            "Verdadeiro num ensaio: uma comparação de configurações que lê a coleção e não escreve "
            "conteúdo arquivístico (ADR 0018). O painel o distingue de uma execução de produção."
        ),
    )
    attempt: int = Field(
        default=1,
        ge=1,
        description="Qual tentativa esta linha é: 1 numa execução pedida uma vez, N numa agendada (ADR 0015).",
    )
    retry_of: int | None = Field(
        default=None,
        description="A execução que esta retenta; nula na primeira tentativa.",
    )
    not_before: datetime | None = Field(
        default=None,
        description="O instante a partir do qual a linha pode ser reivindicada; nulo significa já (ADR 0015).",
    )
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
    runner_id: str | None = Field(
        default=None,
        description="O runner que reivindicou a execução; nulo enquanto ninguém a pegou.",
    )
    started_at: datetime | None = None
    heartbeat_at: datetime | None = Field(
        default=None,
        description="O último sinal de vida do runner, no relógio do banco.",
    )
    lease_expires_at: datetime | None = Field(
        default=None,
        description=(
            "Quando o claim vence se o runner parar de renovar. A próxima varredura do runner "
            "marca a execução como interrompida."
        ),
    )
    cancel_requested_at: datetime | None = Field(
        default=None,
        description=(
            "Quando o operador pediu o cancelamento; nulo enquanto ninguém pediu. É um pedido, não "
            "um estado: a linha continua na fila ou em execução, e segura a vaga, até o worker "
            "honrá-lo no limite do lote."
        ),
    )
    cancel_requested_by: str | None = Field(
        default=None,
        description="Quem pediu o cancelamento; nulo quando o pedido veio de um sinal do processo, não do painel.",
    )
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


class WorkerRunCancelResponse(RouteResponse):
    """
    What a cancellation did, with the row as it stands afterwards.

    Two outcomes share this shape because they differ only in the code: the run was never claimed
    and is already ``CANCELLED``, or it is running and the request is now recorded. The row comes
    back so the screen updates the line it already shows instead of refetching the page.
    """

    data: WorkerRunDTO


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


class WorkerScheduleRequest(RequestModel):
    """A worker's agenda: the cron, the zone and the pinned request it enqueues (ADR 0015)."""

    enabled: bool = True
    cron: str = Field(
        min_length=1,
        max_length=120,
        description="Cinco campos: minuto, hora, dia do mês, mês e dia da semana.",
    )
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description="Nome IANA da zona em que o cron é avaliado; o padrão é DEFAULT_TIMEZONE.",
    )
    request: WorkerRunRequest = Field(default_factory=WorkerRunRequest)


class WorkerScheduleDTO(BaseModel):
    """A worker's agenda, as the panel reads it (ADR 0015)."""

    worker_name: str
    enabled: bool
    cron: str
    timezone: str
    request: WorkerRunRequest
    next_run_at: datetime | None = Field(default=None, description="Nulo enquanto a agenda está pausada.")
    last_enqueued_at: datetime | None = None
    last_skipped_at: datetime | None = Field(
        default=None,
        description="O último período pulado porque o worker já tinha uma execução ativa.",
    )
    updated_by: str | None = None
    updated_at: datetime | None = None


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
    trial_supported: bool = Field(
        default=False,
        description=(
            "Se este worker aceita um ensaio (ADR 0018). A lista é o catálogo: a tela só oferece a "
            "comparação para quem o runner sabe executar."
        ),
    )
    config: dict[str, Any] = Field(default_factory=dict)
    available_engines: list[WorkerEngineDTO] = Field(default_factory=list)
    declared_options: list[WorkerOptionDTO] = Field(default_factory=list)
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
    stamp_breakdown: WorkerStampBreakdownDTO | None = None
    last_run: WorkerRunDTO | None = None
    active_run: WorkerRunDTO | None = None
    schedule: WorkerScheduleDTO | None = None
    runner_available: bool = Field(
        default=False,
        description="Se algum runner online declara este worker; falso não impede enfileirar (ADR 0014).",
    )


class WorkerRunnerDTO(BaseModel):
    """
    One runner process, as the panel sees it (ADR 0014).

    ``online`` is computed by PostgreSQL from the heartbeat and the runner's own declared interval: a
    runner that stopped signalling is still listed — the registry remembers it — but stops counting
    as available for a worker.
    """

    runner_id: str
    name: str
    hostname: str
    version: str | None = None
    capabilities: list[str] = Field(default_factory=list, description="Os workers que este runner aceita.")
    concurrency: int = Field(ge=1)
    started_at: datetime
    last_heartbeat_at: datetime
    stopped_at: datetime | None = None
    online: bool = Field(
        description="Verdadeiro enquanto o último sinal está dentro de três intervalos declarados pelo runner."
    )


class SystemWorkersResponse(BaseModel):
    """The whole panel in one request: the workers, their queues and the runners that drain them."""

    workers: list[WorkerStatusDTO] = Field(default_factory=list)
    runners: list[WorkerRunnerDTO] = Field(default_factory=list)
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


class WorkerTrialRequest(RequestModel):
    """
    A comparison of two or more configurations over one sample, without writing archival content.

    ``sample`` is the random sample of the **production scope** (the units the configurations would
    actually read). The verdict set — the descriptions a person already decided — is read whole up
    to the same cap, because the gabarito is the half that measures quality (ADR 0018). The seed is
    optional and recorded: the same seed and a collection that only grew propose the same rows for
    the rows that already existed.
    """

    sample: int = Field(
        default=50,
        ge=5,
        le=500,
        description="Quantas descrições sortear para distribuição e custo; o gabarito é lido até o mesmo teto.",
    )
    #: The configurations, each with the same shape a run uses. At least two: a comparison of one
    #: configuration is a run, and the screen would have nothing to compare.
    configs: list[WorkerRunRequest] = Field(min_length=2, max_length=4)
    seed: str | None = Field(
        default=None,
        max_length=64,
        description="Semente da amostra; nula usa a do código. Fica registrada no resultado.",
    )


class WorkerTrialMissDTO(BaseModel):
    """One row of the gabarito the configuration got wrong, kept so the disagreement is actionable."""

    description_id: str
    expected: str
    predicted: str
    score: float | None = None


class WorkerTrialSampleDTO(BaseModel):
    """
    What the trial read, recorded so the numbers can be audited after the collection changed.

    ``description_ids`` is the random sample of the production scope; ``verdict_ids`` is the part of
    the gabarito the trial scored. They are different populations on purpose (ADR 0018): the first
    measures the shape and the cost, the second measures whether the labels are right. The ids are
    stored because the collection grows and a seed alone would not reproduce the set.
    """

    seed: str
    size: int = Field(ge=0, description="Quantas descrições a amostra aleatória pediu.")
    description_ids: list[str] = Field(default_factory=list, description="As descrições sorteadas.")
    verdict_ids: list[str] = Field(default_factory=list, description="As descrições com veredito que o ensaio pontuou.")
    verdicts_available: int = Field(ge=0, description="Quantos vereditos existem na coleção; o ensaio lê até o teto.")


class WorkerTrialConfigDTO(BaseModel):
    """
    One configuration of the comparison, with the numbers and the write it would become.

    ``settings`` is the body "use this configuration" sends to the settings route: the trial result
    carries it so the screen cannot reconstruct a different body from the one it measured. The
    metric fields mirror the bench's report — ``agreement`` and ``coverage`` from the verdict set,
    the distribution and the abstention from the production sample, the seconds from the model
    calls only (the load is charged once to the run, not to a configuration).
    """

    engine_name: str | None = None
    preset: str | None = None
    db_batch_size: int | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict, description="A configuração resolvida do engine.")
    settings: WorkerSettingsRequest
    pending: int | None = Field(default=None, description="Unidades que esta configuração poria na fila.")
    pending_reason: str | None = Field(default=None, description="Por que a fila não foi contada.")
    processed: int = Field(ge=0, description="Unidades que o ensaio classificou nesta configuração.")
    verdicts_scored: int = Field(ge=0, description="Vereditos pontuados; o denominador da concordância.")
    answered: int = Field(ge=0, description="Vereditos em que a configuração deu um rótulo (não absteve).")
    agreement: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Acerto sobre o gabarito; nulo quando a coleção ainda não tem veredito.",
    )
    coverage: float = Field(ge=0, le=1, description="Fração do gabarito que a configuração respondeu.")
    abstention_rate: float = Field(ge=0, le=1)
    distribution: dict[str, int] = Field(default_factory=dict)
    largest_share: str = Field(default="", description="O balde mais frequente da distribuição.")
    largest_share_value: float = Field(default=0.0, ge=0, le=1)
    entropy_bits: float = Field(default=0.0, ge=0)
    seconds_per_document: float = Field(default=0.0, ge=0)
    load_seconds: float = Field(default=0.0, ge=0, description="O custo de carregar o modelo, fora dos s/doc.")
    projected_hours: float | None = Field(
        default=None,
        ge=0,
        description="A fila desta configuração no ritmo medido; nulo quando a fila não é mensurável.",
    )
    #: The first disagreements, so "concordância 0.70" has something to open. The list model
    #: carries its own description.
    misses: list[WorkerTrialMissDTO] = Field(default_factory=list)


class WorkerTrialResultDTO(BaseModel):
    """
    What a trial measured: one sample, every configuration, and the numbers side by side.

    ``unknown_verdicts`` names the gabarito labels the active catalogue no longer has. They are a
    guaranteed miss — the engine only answers active names — and reporting them is cheaper than
    letting the reader suspect the model got them wrong.
    """

    worker_name: str
    sample: WorkerTrialSampleDTO
    unknown_verdicts: list[str] = Field(default_factory=list)
    configs: list[WorkerTrialConfigDTO] = Field(default_factory=list)


class WorkerRunDetailDTO(WorkerRunDTO):
    """One execution with its trial result, when it is one."""

    trial_result: WorkerTrialResultDTO | None = None


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


class IngestionOriginHealthDTO(BaseModel):
    """One origin as the health screen needs it: the code, its label and whether it is on."""

    code: str
    label: str
    enabled: bool


class IngestionHealthDTO(BaseModel):
    """The origin table, not the environment: the summary the health screen can trust."""

    ok: bool
    total: int | None = None
    enabled: int | None = None
    origins: list[IngestionOriginHealthDTO] = Field(default_factory=list)
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
    ingestion: IngestionHealthDTO
    process: ProcessHealthDTO
