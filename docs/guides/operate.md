---
sources:
  - src/scrinalia/domains/archive/workers/catalogue.py
  - src/scrinalia/domains/archive/workers/runner.py
  - src/scrinalia/domains/archive/workers/runner_daemon.py
  - src/scrinalia/domains/archive/workers/lease.py
  - src/scrinalia/domains/archive/workers/configuration.py
  - src/scrinalia/domains/archive/workers/ledger.py
  - src/scrinalia/domains/archive/workers/retry.py
  - src/scrinalia/domains/archive/workers/schedule.py
  - src/scrinalia/domains/archive/workers/scheduler.py
  - src/scrinalia/domains/archive/workers/worker_*.py
  - src/scrinalia/domains/archive/worker_stamp.py
  - src/scrinalia/domains/archive/models/operations.py
  - src/scrinalia/domains/archive/models/enums.py
  - src/scrinalia/domains/archive/schemas/system_schema.py
  - src/scrinalia/domains/archive/repository/worker_run_repo.py
  - src/scrinalia/domains/archive/repository/worker_runner_repo.py
  - src/scrinalia/domains/archive/repository/worker_schedule_repo.py
  - src/scrinalia/domains/archive/repository/worker_settings_repo.py
  - src/scrinalia/domains/archive/repository/worker_stamp_repo.py
  - src/scrinalia/domains/archive/services/worker_schedule_service.py
  - src/scrinalia/domains/archive/repository/governance.py
  - src/scrinalia/domains/archive/repository/failure_repo.py
  - src/scrinalia/domains/archive/services/worker_operations_service.py
  - src/scrinalia/domains/archive/services/worker_run_service.py
  - src/scrinalia/domains/archive/services/failure_service.py
  - src/scrinalia/api/controllers/system_controller.py
  - src/scrinalia/api/controllers/ingestion_controller.py
  - src/scrinalia/api/controllers/health_controller.py
  - src/scrinalia/api/controllers/document_controller.py
  - src/scrinalia/core/storage.py
  - src/scrinalia/api/controllers/setup_controller.py
  - src/scrinalia/api/middleware.py
  - src/scrinalia/api/system_health.py
  - src/scrinalia/core/logger.py
  - src/scrinalia/core/config.py
  - src/scrinalia/domains/identity/cli.py
  - src/scrinalia/domains/identity/services/auth_service.py
  - src/scrinalia/domains/ingestion/worker.py
  - src/scrinalia/domains/ingestion/repository.py
  - src/scrinalia/domains/ingestion/sources.py
  - src/scrinalia/domains/ingestion/origin_registry.py
  - src/scrinalia/domains/ingestion/origins.py
  - src/scrinalia/domains/ingestion/origin_repo.py
  - src/scrinalia/domains/ingestion/service.py
  - src/scrinalia/domains/staging/worker.py
  - src/scrinalia/domains/staging/repository.py
  - src/scrinalia/domains/archive/domain/search.py
  - src/scrinalia/domains/archive/repository/document_repo.py
  - src/scrinalia/domains/archive/services/document_service.py
  - testing/evaluation/retrieval_modes.py
  - testing/evaluation/retrieval_quality.py
  - src/scrinalia/core/cli.py
  - src/scrinalia/api/controllers/users_controller.py
  - docs/adr/0009-authentication-and-authorization.md
  - docs/adr/0011-first-run-setup-without-an-open-door.md
  - docs/adr/0014-the-workers-leave-the-api.md
  - apps/curator/src/router.tsx
  - apps/curator/src/routes/SystemWorkersRoute.tsx
  - apps/curator/src/components/workers/**
  - apps/curator/src/routes/SystemHealthRoute.tsx
  - apps/curator/src/routes/OriginsRoute.tsx
  - apps/curator/src/components/ingestion/OriginPanel.tsx
  - .github/workflows/ci.yml
  - mkdocs.yml
---

# Operations

This page is for whoever runs the machine day to day: which workers exist, in which order they run,
how to start the runner or a one-off run, how the effective configuration is resolved, what the
operations panel shows, and what to do when something breaks. Installing and configuring the system
is in [Installation and deployment](install.md); the archival decisions each screen takes are in
[Curation](curate.md).

## The workers and the pipeline order

`src/scrinalia/domains/archive/workers/catalogue.py` is the single definition of a worker: its
position in the pipeline, the unit its queue counts, whether it respects the review governance,
and the stamp it writes. The catalogue imports no worker — it resolves each module lazily — so
reading it is cheap.

Ten workers, in pipeline order:

| # | Name | Module | Unit | Governed | Effective engine from |
| --- | --- | --- | --- | --- | --- |
| 1 | `ingestion` | `ingestion.worker` | origin | no | — |
| 2 | `transfer` | `worker_archive_transfer` | staging record | no | — |
| 3 | `cleaning` | `worker_cleaning_regex` | document | yes | — |
| 4 | `ner` | `worker_ner` | document | yes | signature |
| 5 | `typology` | `worker_typology` | document | yes | signature |
| 6 | `thumbnail` | `worker_thumbnail` | document | yes | — |
| 7 | `conflict-judge` | `worker_resolve_tag_entity_conflict` | tag × entity pair | no | signature |
| 8 | `macro-category` | `worker_macro_category` | tag | no | signature |
| 9 | `quality-validator` | `worker_quality_validator` | document | yes | active `LLM_CHECK` rule |
| 10 | `embedding` | `worker_embedding` | document | no | signature |

The order is the order in which the stages unblock each other, and it is the order the pipeline
section of the panel shows:

```text
ingestion -> transfer -> cleaning -> ner -> typology -> thumbnail -> conflict-judge -> macro-category -> quality-validator -> embedding
```

- **`ingestion`** is the stage in front of the archive: it lists one origin, reads its detail pages
  into `raw_data` and structures the new records into `staging_documents`. Its unit is the **origin**,
  not a document, and it has no engine; each origin is a row with its own queue, agenda and
  configuration, described in [the origins](#the-origins). The host commands
  below still exist for a one-off run, but the panel is the operational path.
- **`transfer`** copies the structured staging record into the archive description, keyed on the
  hash of the parsed record (`staging_content_hash`). It is the only stage that rewrites content:
  when the hash changes, the written `execution_log` is reset and the AI enrichments have to run
  again. A document a human already approved is never overwritten, and a staging record with the
  same hash is not written at all.
- **`cleaning`** applies the active cleaning rules of kind `REWRITE`, one pass per rule. A rule of
  kind `VALIDATE` or `LLM_CHECK` never rewrites anything — flagging is the quality validator's job.
- **`ner`** extracts proper names, places and institutions from the composed document text.
- **`typology`** classifies each description against the active typology catalogue by zero-shot.
  A description whose best score stays under the floor keeps `typology_id` NULL — the column says
  that both when the classifier declined and when no run reached the description — so the refusal
  is recorded instead: a row in `archive_ai_review_queue` with the **score the run saw**.
- **`thumbnail`** downloads the original image and stores a miniature in the object storage. It
  confirms the bucket exists before the first document — creating it only when
  `S3_AUTO_CREATE_BUCKET=true` — so a bucket that is missing fails the run once, with a sentence,
  instead of stamping the whole backlog with the endpoint's misleading `AccessDenied`. `--limit N`
  caps the documents of one run, which is what makes a local test cheap. The worker only writes the
  object; the API serves it on demand through `GET
  /api/v1/documents/{description_id}/thumbnail` (ADR 0017). The endpoint must stay reachable from the
  **API process** and the credentials must allow `GetObject` — the browser never talks to it.
- **`conflict-judge`** compares the tag vocabulary with the entity vocabulary and asks the local
  LLM whether an ambiguous term is a subject or a proper name. Every verdict, auto-resolved or sent
  to a human, leaves a row in `archive_ai_review_queue`. A call the engine could not make raises
  instead of becoming a verdict, so the pair leaves **no** row and is asked again on the next run:
  it is still pending, and the panel's "already judged" number does not count it.
- **`macro-category`** files each tag into a subject category. Its unit is the **tag**, not the
  document, so its stamp lives in the tag's own `execution_log`; a tag a curator filed by hand is
  out of its reach.
- **`quality-validator`** marks structural anomalies, repeated titles and `VALIDATE` rules. It never
  rewrites a field. The language model is only built when an active `LLM_CHECK` rule exists.
- **`embedding`** writes the vector used by semantic search, and reads the text last because every
  text mutation has to happen before it.

!!! note "The embedding is the documented governance exception"
    `embedding` deliberately does not use the `HUMAN_APPROVED` shield. The vector is a derived
    index of the text, not archival content, so an approved description whose text changed must be
    re-embedded or semantic search would serve a stale vector. It writes only the `embedding` column
    and its own stamp, and skips descriptions in `REJECTED`.

### What each queue means

A queue is not a table: it is the predicate the worker's own `count_pending` shares with `execute`.
The panel never re-derives it. `pending` is how many units the next run would read.

For the five workers whose ledger is a stamp, the panel opens the stamp instead of reporting one
number, because an identity slot can hold three different things and only one of them attributes the
answer: **with a producer** is a value the slot's own pattern accepts, a fingerprint that really
names the model; **without a known producer** is a legacy value — the `"DONE"` written before the
fingerprint existed, or the `PRODUCER_UNKNOWN` a migration left in its place; **without a record** is
the key absent, meaning nothing recorded a run at all. `processed` is the first two plus the
failures, and `failed` counts the stamps that record one (`ERROR`; the thumbnail's failure lives under
the `thumbnail_failed` key, because its ledger is not a stamp).

The four numbers are read in **Carimbos (descrições)**, beside the queue and not under it, because
they answer a different question from `pending`: the breakdown is over the worker's **whole ledger**,
while `pending` is the queue predicate, and the two sets are not the same. On the reference
collection the NER card reads **4.831** stamped against **4.813** pending, and the difference is the
**18** descriptions a human approved — the queue applies `ai_writable_documents()`, so a curated
description is counted in the ledger and never in the queue. A reader who took the breakdown as a
decomposition of the queue saw 4.831 where the queue said 4.813 and had nowhere to put the
difference.

Five of the nine stamps carry the **producer identity** instead of a status: a fingerprint of the
engine, the preset, the whole resolved engine configuration, the installed versions of the libraries
of that axis and the declared behavioural options (`force`, `limit` and the reserved `config` stay
out of it). The consequence is the point of the design: changing any of those puts the affected units
back in the queue **by itself**, which a `DONE` could never do — a bump of `torch` used to invalidate
every vector while the stamp stayed current and the queue stayed empty. The embedding composes the
identity with the MD5 of the effective text, so a human edit re-queues it too; the macro-category
composes it with the label-set hash. Two producers are deliberately outside the identity, because
reading them would cost a heavy import or a network call on the panel's path: the spaCy model package
version (`pt_core_news_lg`) and the digest of the model the Ollama server serves. Re-run those two
with `force`.

| Worker | What is pending | Idempotency stamp |
| --- | --- | --- |
| `transfer` | staging records with no archive row, or whose parsed-content hash differs from the archived one — except documents a human approved or rejected | none; a staging-record hash, plus `hierarchy_parent_v1` for a declared parent |
| `cleaning` | documents the active `REWRITE` rules have not stamped yet; a document pending for two rules counts twice | `cleaning_rule_{rule_id}` |
| `ner` | documents that have text in at least one extracted column and no stamp of the current producer | `worker_ner_v2` (value is the producer identity) |
| `typology` | documents with text and no stamp of the current producer — the stamp signs the active label set, so adding, renaming or retiring a typology reaches the documents already classified | `worker_typology_classifier_v2` (value is the producer identity) |
| `thumbnail` | documents with a source image, no storage URI and no failure mark — every marked one, with `force` | none; the `storage_thumbnail_uri` column, plus the `thumbnail_failed` mark |
| `conflict-judge` | **not measurable cheaply**: the queue is the trigram product of tags × entities, measured at 53 s on the real collection. The panel shows what was already judged | none; the `archive_ai_review_queue` row |
| `macro-category` | tags with no subject category whose stamp is not the current producer (the label set and the model are both in it) | `worker_macro_category_v1` (on the tag; value is the label set composed with the producer identity) |
| `quality-validator` | documents without the stamp of the current producer, unless `force` is on | `worker_quality_validator_v1` (value is the identity of the active `LLM_CHECK` rule, or of "no model" — including a rule whose engine cannot be built, which is the run the validator actually makes) |
| `embedding` | documents whose stamp differs from the MD5 of the effective text **plus** the producer identity — the first run, every later text change and every model or dependency bump | `worker_embedding_v1` (value is the MD5 followed by `:` and the identity) |

A document the worker marked `ERROR` stays out of the plain queue: `force` is the way back, and it
clears the mark on the units it processes. A unit stamped by a producer that is no longer configured
is pending again — including every legacy value, whether it still reads `"DONE"` or the
`PRODUCER_UNKNOWN` the migration renamed it to. Those rows were pending before the rename and are
pending after it, so the migration changed what the ledger **says** and not what the queue **does**:
the next run heals them by writing a real fingerprint. That is the whole point of the distinction —
attribution and reporting, not the queue. The typology identity signs the active label set as
well, so after this upgrade **every** stamped description is pending once, typology or not: the whole
ai-writable collection on the first run, and from then on only what a catalogue, model, column or
floor change actually moved. The preview below is how to size that before paying it.

The `transfer` counter is the heaviest one: it validates the whole staging table through the same
port the transfer uses. It is read once per panel load and is not polled in a loop.

## The runner

Since ADR 0014 the workers run in their own process; the API only enqueues. The runner claims the
`QUEUED` rows and executes them:

```bash
uv run python -m scrinalia.domains.archive.workers.runner_daemon \
    --name gpu-01 --workers ner,typology,embedding
```

| Flag | Meaning |
| --- | --- |
| `--name` | the human name in the panel; the identifier is generated (`name:<short uuid>`) unless `--id` is given |
| `--workers` | the workers this runner accepts, comma-separated; the default is the whole catalogue |
| `--concurrency` | how many runs it executes at once; 1 by default, because the models are CPU/GPU-bound |
| `--heartbeat-seconds`, `--lease-seconds` | the lease it renews and how long a claim survives without it; 15/60 by default, and the heartbeat must be smaller |
| `--poll-seconds`, `--sweep-seconds` | how often it looks for work and how often it expires claims; 2/30 by default |
| `--once` | claims and runs at most one execution, then exits |
| `--drain-seconds` | waits up to that long for in-flight runs before exiting; the lease covers the rest |

The runner registers in `archive_worker_runners`, renews its own row with the same heartbeat, and
refuses to start against a schema behind its code. The panel shows it — online/offline, the host, the
version, the capabilities — and marks **sem runner** the workers no online runner accepts; a run
enqueued for one of those waits. The database is the only channel: the API never calls a runner.

## Running a worker

### The unified runner

Prefer the unified runner, which exposes every worker behind one interface. Run it from the
repository root:

```bash
uv run python -m scrinalia.domains.archive.workers.runner <name> \
    [--engine X --preset Y --batch N --limit N --option key=value --engine-option key=value --by "who"]
```

For example:

```bash
# Classify the typology of every pending description, in batches of 100.
uv run python -m scrinalia.domains.archive.workers.runner typology \
    --engine deberta_typology --preset cpu_local --batch 100 --by "ana"

# Try a threshold measured by the bench on the first 200 descriptions only.
uv run python -m scrinalia.domains.archive.workers.runner typology \
    --option confidence_threshold=0.6 --limit 200 --by "ana"

# Force the embedding of every description, ignoring the text hash.
uv run python -m scrinalia.domains.archive.workers.runner embedding --option force=true

# Override the engine's device for this run only: a pass-through to the engine constructor.
uv run python -m scrinalia.domains.archive.workers.runner ner \
    --engine spacy_ner --engine-option device=cpu --by "ana"
```

| Flag | Meaning |
| --- | --- |
| `<name>` | one of the nine names above; any other value is refused with the list of options |
| `--engine X` | a registered engine of the worker's axis, e.g. `spacy_ner`, `deberta_typology`, `ollama_judge` |
| `--preset Y` | a preset of that axis, e.g. `gpu`, `lemmatizer`, `cpu_local`, `gpu_cloud`, `xlm_roberta_local`, `gemma_4b_local`, `multilingual_minilm` |
| `--batch N` | batch size per transaction, forwarded to the workers that declare `db_batch_size`; a worker without it logs that the value was ignored |
| `--limit N` | cap on the units this run touches, for the workers that declare `limit` (`embedding`, `macro-category`, `ner`, `quality-validator`, `thumbnail`, `typology`); refused for the others, because a cap that silently does nothing is worse than no cap. It counts attempts, so a queue of failures still ends, and it is never persisted |
| `--option key=value` | a **declared** worker option, repeatable; a key the worker does not declare is refused with its option list, and `key` without `=` is refused |
| `--engine-option key=value` | a raw pass-through to the engine constructor, repeatable, for one run; never persisted, and its keys are not enumerated (the engine validates the value) |
| `--by "who"` | free text naming who is running it; the CLI runs on the host and has no session, so this stays a name with no account behind it |

`--option` is validated against the worker's `execute` signature, and coerced by the type the worker
declares there: `true`/`false` become booleans, an integer default makes the value an `int`, a float
default a `float`. `--option confidence_threshold=0.6` therefore arrives as a number and reaches the
comparison; a value that cannot be read (`0.6x` for a float, `talvez` for a boolean) is refused with
a sentence before the run starts, instead of failing at the bottom of it. A key the worker does not
declare is refused: `--option colunas_to_classify=…` — the measured typo of #120 — is a `422`
sentence naming the options the worker does take, and not a default that fails later in the queue
counter. A column list is checked against the columns the AI text has (below).

`--engine-option` is the **named exception**: it goes straight to the constructor of the engine, for
whoever knows the library. It is per run and never persisted, so a tweak does not become an
installation default; the keys the axis itself passes are offered as a hint
(`model`, `device`, `host`, `batch_size`, `dimensions`, `disable`), and a key outside them is still
forwarded — the engine is the one that validates the value. Only a worker whose `execute` ends in
`**engine_kwargs` has the door; `transfer`, `cleaning`, `thumbnail` and `conflict-judge` declare no
pass-through, and the run is refused if one is given.
`conflict-judge` therefore takes its host from the `OLLAMA_HOST_URL` setting (or the local default),
not from a flag.

Five things are always refused:

- `config` is a runner dataclass (`NerRunnerConfig` and its siblings), not a value a command line or
  a JSON body can carry; a dictionary reaching `execute` would fail with an attribute error instead
  of a sentence. Pass the individual fields instead.
- `source` and `storage` are **ports** (the staging source, the object storage), and `db`/`db_session`
  is the session the runner opens: none of them travels through JSON.
- `engine_name`, `preset` and `db_batch_size` have a field of their own. They are refused inside
  `options` because the runner applies the extra mapping *after* the resolved argument, which made a
  value there a silent second definition of the same field.
- `limit` is refused as a **persisted default** (`PUT …/settings`): it caps one execution, and a cap
  that outlived the command would stop every later run at N units. `force` is a legitimate default —
  it is the way back from a mark a transient outage left behind.
- `--engine`/`--preset` only make sense for the workers whose configuration comes from their
  signature (`ner`, `typology`, `conflict-judge`, `macro-category`, `embedding`). `transfer`,
  `cleaning` and `thumbnail` load no model, and `quality-validator` takes its engine from the active
  `LLM_CHECK` rule.

Every run through the runner writes a row to `archive_worker_runs` (see
[the run ledger](#the-run-ledger)).

### Running a worker module directly

Each `worker_*.py` also carries an `execute(db, ...)` function and a `__main__` block, so a single
worker can be run while developing:

```bash
uv run python -m scrinalia.domains.archive.workers.worker_ner
```

A direct run is a debugging tool, not the operational path. It bypasses the ledger, the persisted
overrides, the concurrency guard and the `--option` coercion, and it uses whatever `engine_name`
and `preset` the module's `__main__` block hardcodes (for `ner`, `db_batch_size=100` and otherwise
the signature defaults). Nothing appears in the run history, so nothing tells you it happened.

### The origins

An origin is a definition in code plus a row in `ingestion_origins` (ADR 0016). The definition — its
adapter and the `SourceSchema` that says which of its labels fills which staging column — stays next
to the adapter; the row is the lifecycle: enabled/paused, the URLs, the run policy a scheduled
execution inherits, and the cron/zone of its agenda. The `manual` and `csv` definitions are **entry
paths**, not sources: they have no adapter and are never offered by the picker. Their rows exist for
provenance and for the form/import, and the page shows them read-only. Adding a source is a module
and a registry entry; the row is added from the screen, and the staging transform learns no site.

`/sistema/ingestao` is the screen, and it has two sections (#206). **Origens** lists the configured
sources, one card each: the queue the next execution would read, the processed/failed numbers, the
last and active run, the agenda, the effective configuration and the runner availability. The
operator can **Adicionar origem** — a picker of the definitions the package ships and this
installation has no row for; adding activates — **Configurar**, **Agenda**, **Desativar/Ativar** and
**Enfileirar execução**. **Configurar** and **Agenda** are the card's two panels: the click opens the
card, shows the form and brings it into view, and a second click closes the form and leaves the card
open. Pausing is the lifecycle, not a removal: the card, the agenda and the runs
stay, and only the run is refused. A fresh install starts with no configured source (the seeded
`pmc` row is dropped by `f1090f825a94`), so the section shows **Nenhuma origem configurada** and the
add flow. **Entradas** lists the manual and CSV rows read-only, with their status and a link to
`/acervo/nova`: they are the entry paths, not sources.

The two ways into the collection are the tabs of `/acervo/nova` (#205). The generic worker routes
refuse `ingestion`: a run of it needs an origin, so the origin routes are the selector
(`/api/v1/ingestion/origins/...`).

The card is an `OPERATE` one: the operator owns adding, configuring, scheduling, pausing and running.
The read routes stay authenticated, so a curator who follows a direct URL still sees the cards
read-only, with the operator controls hidden; the ordinary door to the collection is `/acervo/nova`.

The stage runs in the **same** ledger, runner, lease and cancellation as the AI workers. A run has
`worker_name="ingestion"` and `origin_code` set; the partial unique index is
`(worker_name, COALESCE(origin_code, ''))`, so the archive workers keep one slot per worker while each
origin has a slot of its own. The scheduler reads the due origins and enqueues one run per origin; a
period that arrives while that origin is already running is skipped, and a failed scheduled run is
retried by the existing policy.

The host commands remain for a one-off run, and they now always name the origin:

```bash
# List the origin's identifiers into the queue, walking at most ten listing pages.
uv run python -m scrinalia.domains.ingestion.worker discover --origin pmc --pages 10

# Read the detail page of at most a hundred of the identifiers the queue holds.
uv run python -m scrinalia.domains.ingestion.worker scrape --origin pmc --limit 100

# Both phases, then the staging transform, in one process.
uv run python -m scrinalia.domains.ingestion.worker run --origin pmc --pages 10 --limit 100

# Structure raw records into staging; with no --origin, each record resolves its own schema.
uv run python -m scrinalia.domains.staging.worker --limit 100
```

`--origin` is **required** for the ingestion commands and there is still no default:
`ACERVO_SOURCE` was removed. The reference adapter accepts `PUBLIC_SCRAPE_URL` and
`PUBLIC_SCRAPE_DETAIL_URL` as a fallback for its URLs, which is what keeps an existing `.env`
working; the origin's row wins when it has a value. `scrape` also takes `--audit-ttl-days N` to re-read
the descriptions completed more than N days ago, `--force-retry-fatal` to include the rows marked
`FATAL_ERROR`, `--ignore-sliding-window` to drop the discovery and TTL windows, and `--max-retries`,
`--discovery-window-days` and `--scraped-ttl-days` to override the run policy for that run only.

**A bounded run resumes by itself.** The queue is ordered by `last_scraped_at`, never-tried first,
and every outcome — done, a transient failure, a fatal one — stamps it, so the batch that just ran
moves behind the ones that have not. The transform is keyed on the hash of the parsed record, so
whatever a run structured stops being pending. `--limit 100` over a queue of thousands therefore
takes the next hundred on the next run, and both commands log how much is still pending when they
finish. The one exception is a scrape whose write rolls back: the row keeps its place and holds a
slot of every run until the write succeeds.

`--force` re-parses every raw record, which is what a parser fix needs, and it also bypasses the
comparison the transform advances on, so a bounded forced run is not resumable by itself. That is
what `--after <description_id>` is for: the run logs the id its window ended at and the command to
continue from there. Do not use `--after` without `--force`: under the comparison, skipping ahead
would skip pending records instead of already-structured ones.

### The manual entry

The `manual` origin is the **Digitar** tab at `/acervo/nova` (the old `/sistema/ingestao/nova`
redirects there), and it is **not** an approval. The submit writes `raw_data` (with `created_by`), a
`scraping_queue` row marked `DONE` (the form is the discovery) and the staging record, then enqueues
the same `transfer` worker the scraper uses. The archive description is born `PENDING_AI`, and the AI
queues see it; the archivist approves in the dossier after the AI runs. If a transfer is already in
flight, the record stays staged and the response says it enters the next one. A duplicate
`description_id` is refused before the write; the form generates a `manual-<uuid>` id so a retried
submit is the same record.

The form is the first tab of the entry screen, at `/acervo/nova`; the CSV import is the second. The
record is the whole ISAD(G) record — thirty controls grouped in the norm's seven areas, identity open
and the rest collapsed — and it shares the screen with the import because both feed the same staging
and the same queue, not because the two are the same input. The labels, kinds and order come from the
same catalogue the dossier edits (`apps/curator/src/lib/isad.ts`), so the two screens cannot grow two
vocabularies for one norm.

Three behaviours are worth knowing before typing:

- **The date is text.** The archivist types what the record says (`Década de 1980`, `1951-1953`) and
  the language profile parses it — the same grammar the CSV import uses. A value the profile cannot
  read is refused with a sentence instead of becoming an empty date, and the confirmation repeats the
  date the profile read, so what was stored is visible.
- **The level and the language are selects.** The level comes from the level catalogue and the
  language from `GET /api/v1/languages` (a catalogue declared in code — a language carries no rule an
  institution edits). A rung that requires a parent and has none **warns and still submits**: the
  record enters pending and the dossier's arrangement tab links it later.
- **The digital object is disabled.** The upload control is rendered disabled, with the sentence
  that points at #198: the archive keeps the description and not the file. The image URL below it is
  the one path that works today — the thumbnail worker copies that image into the storage.

### The CSV import

The `csv` origin is the **Importar CSV** tab at `/acervo/nova?modo=csv`, and it is a write of the
same kind as the manual entry: the rows are staged and one `transfer` is enqueued, so the archive
description is born `PENDING_AI` (#191, ADR 0019).

The file never reaches the server as a file. The browser parses it (comma or semicolon, quoted
fields, CRLF, UTF-8 with a Windows-1252 fallback), maps the detected headers to the origin's declared
labels and shows a preview; only a **bounded list of rows** is sent as JSON to `POST
/api/v1/ingestion/csv`. There is no multipart route and no object storage in this path: an
installation whose thumbnail bucket is unconfigured imports a CSV exactly the same.

`GET /api/v1/ingestion/csv/spec` publishes the map and the bounds — the label, the staging attribute,
the required flag and the per-field cap of every column, plus `max_rows`, `max_bytes`, `max_row_bytes`
and `max_field_chars`. The values live in `domains/ingestion/csv_import.py`, one definition; the route
refuses a request over them with a **413** and a sentence.

The API is the authority, not the screen: every row is validated with the same `StagingDocumentDTO`
and `SourceSchema` the staging transform uses, and the answer reports each row as **accepted**,
**duplicated** (the `description_id` already exists in `raw_data`, `scraping_queue` or the archive) or
**invalid** (missing title, an unreadable date, an unknown field, a value over the limit), with the
file's line and the field. A partial import is a normal outcome, not an error. The accepted rows are
written as `origin_code='csv'` and staged in one run; if a transfer is already in flight the response
says the rows enter the next one. Re-importing a file without the `Identificador` column creates new
records — the column is optional and the screen generates a `csv-<uuid>` when it is absent.

## Configuration: what a run actually uses

The effective configuration follows one precedence:

```text
explicit argument  >  archive_worker_settings row  >  the worker's signature default
```

The persisted row (`archive_worker_settings`, one row per worker, keyed by `worker_name`) is
**partial on purpose**: a field left `NULL` keeps following the code, so a preset renamed in a new
release still reaches every worker nobody overrode. Its fields are `engine_name`, `preset`,
`db_batch_size`, `options`, `updated_by` and `updated_at`.

Every write leaves a revision in `archive_worker_settings_revisions` (`before`, `after`,
`changed_by`, `changed_by_user_id`, `changed_at`), written in the same transaction as the row. You
can read them at `GET /api/v1/system/workers/{worker_name}/settings/revisions`. Deleting the row
(`DELETE /api/v1/system/workers/{worker_name}/settings`) makes the worker follow the code again, and
is idempotent.

`GET /api/v1/system/workers` is the way to see the effective configuration without running
anything. Each worker carries the resolved `engine_name`, `preset`, `db_batch_size`, `options`,
`overridden` (whether a row exists — a field can be `None` on purpose), the resolved `config`
dictionary, the `available_engines` with their presets, and a `note`. That dictionary comes from
`describe_config` in each engine registry, the **read-only twin of `get_engine`**: it resolves the
preset and the overrides and returns the dictionary without instantiating the engine, so the panel
can answer "with which model will this run?" for a worker that never ran — without loading the
model.

For `quality-validator`, `engine_source` is `llm_check_rule`: the engine and preset come from the
active `LLM_CHECK` rule, and the settings and trigger routes refuse to set them there, because a
second place to choose the same engine would be a second source of truth. When no rule is active the
worker runs deterministic validation only, and the panel says so in `note`.

### What a worker accepts

What a worker accepts is its `execute` signature, and the API publishes it: `GET
/api/v1/system/workers` and `/workers/settings` carry `declared_options` — the name, the kind of
control (`boolean`, `integer`, `number`, `text`, `list`, `columns`), the signature default, whether
the option is a persisted default or one execution's (`scope: "run"` for `limit`) and, for a column
list, the values it admits. The configuration and run screens render that list as fields, so the form
cannot offer a key the write path would refuse, and the archivist does not have to know that the
parameter is called `columns_to_classify`.

Two option names carry the text an AI worker reads: **`columns_to_extract`** (`ner`) and
**`columns_to_classify`** (`typology`). Their values are the columns in `AI_TEXT_COLUMNS`:

`original_title`, `final_title`, `scope_content`, `admin_bio_history`, `provenance`.

That tuple is the one definition of what the AI may read: it is what the SQL composition composes,
what the evaluation benches check in `--config engine:preset:columns` and what the write path checks
in the option. A name outside it is refused when the default is saved, with the known ones in the
sentence; an empty list is refused too, because a worker with no column has no text to read. Leaving
the field empty keeps the code default (`NerRunnerConfig.columns_to_extract`,
`TypologyRunnerConfig.columns_to_classify`), which is the value the run ledger records.

A row saved before this rule is not a new mistake: the read ignores the option it can no longer
honour and puts the reason in `note` ("Padrão salvo ignorado — …"), so the panel answers with the
code default instead of failing the queue counter. Saving the screen again heals the row.

### Trying a configuration before saving it

A saved default is not only a preference: because the queue is keyed on the producer identity,
changing the engine, the preset or a declared option (a `confidence_threshold`, the columns read)
puts units back in the queue by itself. `POST /api/v1/system/workers/{worker_name}/queue/preview`
answers how many, for a configuration that was never written, with the same precedence a run uses.
The body is the settings body, so the screen previews exactly what it would save, and the answer is
`pending` plus a `pending_reason` for the worker whose queue is not measurable (`conflict-judge`).

Measured on the reference collection, with the typology's documents stamped by the producer in the
code: the default configuration answers `0 na fila`, and proposing `{"confidence_threshold": 0.9}`
answers `4.465` — the floor is part of the identity, so the documents the 0.40 floor settled are
pending under the 0.90 one, and nothing was saved. That number is also what the next run would cost,
which is why the settings screen puts it behind *Conferir impacto* instead of leaving it to be
discovered after the write.

The CLI has no preview route; `--limit N` on a run is the other way to bound the same cost.

### Comparing configurations on a sample

The preview answers *how many* units a configuration would read. It does not answer *whether the
labels are right*, and that is the question that produced #70: the typology was run over 4,844
descriptions with a configuration nobody had measured, and re-running it is expensive. A **trial**
answers it without writing the collection (ADR 0018).

`POST /api/v1/system/workers/{worker_name}/trial` takes the sample size, two to four configurations
(each with the same `engine_name`/`preset`/`db_batch_size`/`options` shape a run uses) and an
optional seed, and queues **one** ledger row with `trial=true`. The runner executes the
configurations sequentially inside that row, over the same sample, and stores the result in the
row's `trial_result`. A trial:

- **writes no archival content** — no `typology_id`, no stamp, no review-queue row. The executor
  shares the worker's text composition, engine registry and decision rule (`score >
  confidence_threshold`) but never calls `execute`;
- **holds the worker's slot**, because it loads the model and reads the collection, and the panel
  shows it as an `ensaio`; the panel's "last run" is a production run, never a trial;
- is cancellable like any run, and is never retried.

Two populations are measured, and they are different on purpose:

- the **gabarito** is the human decision already recorded: the latest `archive_document_revisions`
  row that changed `typology_id` (the dossier, or filing a refusal), and the current catalogue name
  it points to. `HUMAN_APPROVED` is **not** a verdict — approving a record is not certifying every
  label in it. Agreement (the share of verdicts the configuration got right, with the denominator
  shown) and coverage (the share it answered instead of abstaining) are measured here;
- the **production scope** is a seeded random sample of the ai-writable descriptions the
  configurations would read (the intersection of their non-stamp predicates). The distribution, the
  abstention rate, the entropy and the seconds per document are measured here, because the gabarito
  is a hard set and not the mix the next run will pay for.

The engine is built once per `(engine, preset, engine options)` and shared, so a configuration that
only changes the floor does not pay the model load twice. A fresh installation has no human typology
verdict and the screen says so instead of printing an agreement over an empty set. A typology that
has been retired from the active catalogue is a guaranteed miss (the engine can only answer active
names) and the result names it.

The comparison produces the choice; it does not become the choice. **Usar esta** sends the
configuration's own `settings` body — the one the trial measured — to `PUT
/api/v1/system/workers/{worker_name}/settings`, so the default keeps living in one row. **Rodar no
acervo inteiro** then reads the pending count of the saved body (`queue/preview`, after the write)
and triggers the real run with an **empty** request, so the precedence resolves the row that was just
saved: the number on the screen is the number the run will read.

`limit` and `engine_options` are refused inside a trial configuration: the first is a cap for one
execution and the second is a raw pass-through to the engine constructor, and neither is a persisted
default — a comparison has to be of something the screen can save. Today the trial exists for the
typology worker; the route refuses the others, and the configuration screen only offers the card
where the catalogue says `trial`.

## The operations panel

The panel is the `/api/v1/system/*` surface and the four cards of `/configuracoes`, under *Operação*,
in the SPA: the menu no longer carries them (issue #22).

| Route | Method | Permission | What it does |
| --- | --- | --- | --- |
| `/api/v1/system/workers` | `GET` | authenticated | the ten workers with configuration, queue numbers, last/active run and the runner registry, in one request |
| `/api/v1/system/workers/settings` | `GET` | authenticated | the persisted defaults of the AI workers, without the queue counters (issue #53) |
| `/api/v1/system/workers/{worker_name}/queue/preview` | `POST` | authenticated | the pending count of a **proposed** configuration, computed without writing |
| `/api/v1/system/workers/{worker_name}/runs` | `POST` | `OPERATE` | queues one run with per-run overrides and answers `201` immediately |
| `/api/v1/system/workers/{worker_name}/trial` | `POST` | `OPERATE` | queues a trial: two or more configurations over one sample, writing no archival content (ADR 0018) |
| `/api/v1/system/workers/{worker_name}/schedule` | `GET` | authenticated | the worker's agenda, or null when it has none (ADR 0015) |
| `/api/v1/system/workers/{worker_name}/schedule` | `PUT` | `OPERATE` | creates or replaces the agenda: the five-field cron, the IANA zone, the pinned request and the enabled state |
| `/api/v1/system/workers/{worker_name}/schedule` | `DELETE` | `OPERATE` | removes the agenda; the runs it already created stay in the ledger |
| `/api/v1/system/workers/{worker_name}/settings` | `PUT` | `OPERATE` | persists the default engine/preset/batch/options |
| `/api/v1/system/workers/{worker_name}/settings` | `DELETE` | `OPERATE` | drops the override so the worker follows the code |
| `/api/v1/system/workers/{worker_name}/settings/revisions` | `GET` | authenticated | who changed what, when |
| `/api/v1/system/runs` | `GET` | authenticated | the execution ledger, newest first; filters `worker`, `origin`, `status`, `fingerprint`, `trial`, `limit`, `offset` |
| `/api/v1/system/runs/{run_id}` | `GET` | authenticated | one execution, with its trial result when it is a comparison (ADR 0018) |
| `/api/v1/system/runs/{run_id}/cancel` | `POST` | `OPERATE` | asks one execution to stop: closes a queued run no runner claimed, records the request on a running one (#72) |
| `/api/v1/system/failures` | `GET` | authenticated | the grouped root causes; filters `days` (default 30), `worker`, `limit` |
| `/api/v1/system/health` | `GET` | `OPERATE` | database, Ollama models, object storage, the ingestion origins and the process |
| `/api/v1/ingestion/origins` | `GET` | authenticated | every origin with its own queue, its last run and its agenda (#44) |
| `/api/v1/ingestion/origins/{code}` | `PATCH` | `OPERATE` | the origin's lifecycle and adapter configuration (URLs, espera) |
| `/api/v1/ingestion/origins/{code}/schedule` | `PUT` | `OPERATE` | the origin's cron and IANA zone |
| `/api/v1/ingestion/origins/{code}/schedule` | `DELETE` | `OPERATE` | removes the origin's agenda, keeping its configuration |
| `/api/v1/ingestion/origins/{code}/runs` | `POST` | `OPERATE` | queues one ingestion run for the origin, with per-run options |
| `/api/v1/ingestion/manual` | `POST` | `CURATE` | writes one typed record, stages it and queues the transfer |
| `/api/v1/ingestion/csv/spec` | `GET` | authenticated | the CSV map, the field caps and the row/byte limits (#191) |
| `/api/v1/ingestion/csv` | `POST` | `CURATE` | imports a bounded list of CSV rows, stages the accepted ones and queues one transfer (#191) |

Only `ADMIN` carries `OPERATE`; `CURATOR` and `VIEWER` can read the workers, the ledger and the
failures, but cannot trigger a run or change a default. The manual entry and the CSV import are the
ingestion writes a curator owns (`CURATE`): typing a record or importing a spreadsheet is curation,
while pointing an origin at a site or starting a crawl is operation.

The SPA mirrors it, as cards of `/configuracoes` under *Operação*:

| Screen | Shows |
| --- | --- |
| `/sistema/workers` | the operations screen, with two tabs in the URL (#207). **Painel**: the ten workers — engine, preset and model, the queue, what the stamp of each one names (with a producer, without a known one, without a record) and an **Enfileirar execução** button; above them, the runner cards (online, host, version, concurrency, capabilities, last heartbeat) and a warning when none is online. A worker no online runner accepts is marked **sem runner** — the row still queues and waits. The **Agenda** badge and fact show the cron, the zone, the next run and the last skipped period. The effective configuration is read-only here. The `ingestion` row is the exception: it has no engine, no aggregate pending/processed/failed counters, and its run belongs to an origin, so it links to `/sistema/ingestao` instead of a generic run button — the per-origin numbers live on that screen. The last run is a link to the ledger, filtered by that worker and with the exact row highlighted. **Execuções**: the execution ledger, and the failures of the last 30 days grouped by root cause; clicking a cause filters the ledger to its occurrences. Each row says who asked (`painel`, `linha de comando` or `agenda`), the attempt (`tentativa 2/3`), the row it retries and, when it is queued with a `not_before`, when it starts. A **trial** row carries an `ensaio` badge and links to the comparison card, so it is never mistaken for a production run (ADR 0018). An active row offers **Cancelar execução…** with an inline confirmation, and a requested stop is shown as a note while the worker finishes the current batch. The old `/sistema/execucoes` path redirects here with the search preserved |
| `/configuracoes/workers` | the persisted default of each worker and its revisions, with save and remove, and the worker's **Agenda** (the cron, the zone, the enabled state and the pinned request) — the write the panel used to carry. A worker the catalogue marks `trial` (today the typology) also carries **Comparar configurações**: two configurations, the sample size, the side-by-side table (agreement with its denominator, coverage, abstention, the largest drawer, entropy, seconds per document, the queue and the projected hours) and **Usar esta**, which saves the measured body, and **Rodar no acervo inteiro**, which reads the saved body's queue and triggers the real run |
| `/sistema/ingestao` | **Origens**, one card per configured source: its queue and last run, the adapter configuration, the agenda, **Desativar/Ativar** and **Enfileirar execução**; **Adicionar origem** opens the picker of the definitions without a row. The **Entradas** section shows the manual/CSV rows read-only, with a link to `/acervo/nova`. The card is `OPERATE`; the read routes remain authenticated (#206) |
| `/sistema/diagnostico` | database, Ollama models, thumbnail storage, the ingestion origins (active/total, with a link to `/sistema/ingestao`) and the effective process configuration |

Only the active tab is mounted, so only its read is polled: the panel every 5 s while a run is
running and every 15 s while one is queued (the `transfer` counter makes one `/system/workers` call
cost about two seconds on the real collection), and the ledger every 5 s while an entry is active —
idle, neither polls. `/configuracoes/workers` reads `/system/workers/settings`, which resolves the
same configuration and counts no queue — the split exists so that a screen showing no numbers does
not pay for them.

### Health: three endpoints, three questions

They are not interchangeable, and merging them is the mistake to avoid.

| Endpoint | Question | Behaviour |
| --- | --- | --- |
| `GET /health/live` | is the process alive? | touches nothing, always `200` while the process answers; excluded from the OpenAPI document |
| `GET /health/ready` | may this instance receive traffic? | runs `SELECT 1`; `200`, or `503` when the database does not answer; also outside `/api/v1` and outside the contract |
| `GET /api/v1/system/health` | which piece is down? | the human panel: database counts, the Ollama models the presets require and which are missing, the object-storage bucket, the `ingestion_origins` summary, and the effective process configuration — secrets as presence, never as value |

The ingestion card reads `ingestion_origins`, not `PUBLIC_SCRAPE_*`: since #44 an origin is a row, so
an installation can have `pmc` configured with an empty `.env`. It counts only the **configurable**
origins (#206): the manual/CSV entries and a code that left the registry are not sources, so they are
not in the number. The process card labels the variable as a **fallback** for the reference adapter,
and the per-origin queue, agenda and counters stay on `/sistema/ingestao`.

A liveness probe that consults the database would restart the API whenever the database restarts,
which is why `live` touches nothing. The readiness probe owns its own engine with a connection and a
statement timeout, so a probe against an unreachable host fails fast instead of hanging for the
operating system's TCP timeout.

## The run ledger

`archive_worker_runs` has one row per execution, for **both** the CLI and the panel: the ledger is
about the worker, not about the button that started it. A row carries `worker_name`, `origin_code`
(the origin an `ingestion` run processed; null for an archive worker), `status`,
`trigger` (`CLI`, `API` or `SCHEDULE`), `trial` (whether the execution is a comparison, ADR 0018),
`requested_by` (and `requested_by_user_id`), `engine_name`, `preset`,
the validated `request` (what a runner reproduces), the resolved `config`, the **effective worker
`options`**, `queued_at`, `runner_id`, `started_at`, `heartbeat_at`, `lease_expires_at`,
`cancel_requested_at`, `cancel_requested_by` (and `cancel_requested_by_user_id`), `finished_at`,
`duration_ms`, `error`, the generated `error_fingerprint` and, on a trial, the `trial_result` JSONB.

`config` answers "with which model?" and `options` answers "over which text, with which floor?" —
the two halves of one run. `options` is resolved **when the run starts**, because the default of a
column list lives in the worker's own runner dataclass and only the worker can say which columns it
read; a row queued but not started, or written before the column existed, carries the empty default
and the ledger screen says "opções não registradas nesta execução". The producer identity hashes the
same values into the stamp, so the row is the readable half of that hash.

A trial is the exception the schema makes explicit: it carries no single `engine_name`/`preset`/
`config` (the configurations are in its `request`, and their resolved values are in
`trial_result.configs`), it writes no archival content, and it is the only row that may have a
`trial_result`. The panel's "last run" of a worker filters `trial = false`: an experiment is not the
work the worker last did. A trial still holds the worker's slot and appears as the active run while
it executes, because it loads the model and reads the collection.

The statuses are `QUEUED`, `RUNNING`, `SUCCESS`, `FAILED`, `INTERRUPTED` and `CANCELLED`. The `QUEUED`
row is committed through the ledger's **own session before the request returns**, so an external
runner can claim it; the claim is one statement (`FOR UPDATE SKIP LOCKED`) that also writes `runner_id`,
`started_at`, `heartbeat_at` and `lease_expires_at`. A `QUEUED` row is the work item; the API only
enqueues.

A cancellation is a **request** before it is a status: `cancel_requested_at` (and
`cancel_requested_by`, with its `_user_id` link) is written while the row is still `QUEUED`/`RUNNING`,
and only the worker's batch boundary turns it into `CANCELLED`. [Cancelling a run](#cancelling-a-run)
is the whole story.

`uq_worker_run_active` is a **partial unique index** on `(worker_name, COALESCE(origin_code, ''))`
where the status is `QUEUED` or `RUNNING`. It, and not a process lock, is the concurrency guard: at
most one run per worker may be in flight, across processes and across a reload. The origin in the
key is what gives each ingestion origin a slot of its own without weakening the archive workers'
one-slot-per-worker rule (their `origin_code` is null and coalesces to one value). A second submission becomes an
`IntegrityError` that the API turns into `409` with a sentence ("Já existe uma execução em
andamento para o worker '…'"). The CLI reaches the same error but has no handler for it, so it stops
with a traceback instead of the sentence.

A runner claims a `QUEUED` row and renews the lease while it runs; `--concurrency` decides how many
it executes at once, and the workers are CPU/GPU-bound, so one is the default. The runner is **not**
the scheduler: the cron and the retry belong to the scheduler (see [Scheduling and
retries](#scheduling-and-retries)). The queue is one slot per worker, so a second run waits in the
ledger or answers `409`.

## Reprocessing a document or a batch

Re-running a worker is safe and incremental: its queue is the absence of the stamp of its current
producer, so a second run touches only what is still pending. What puts a unit back in the queue:

- **the text changed** — a human edit or an approved/edited/undone text excerpt. `embedding`
  re-queues by itself because its stamp carries the MD5 of the effective text; the text-dependent
  stamps (`worker_ner_v2`, `worker_typology_classifier_v2`, `worker_quality_validator_v1`) are
  invalidated by the text-quality service.
- **the producer changed** — another engine, preset, `confidence_threshold`, column set, an upgrade
  of `torch`/`transformers`/`sentence-transformers`/`spaCy`, or the `LLM_CHECK` rule the
  quality-validator takes its engine from. All of it is inside the identity, so the affected units
  return by themselves; the preview above says how many before the change is saved.
- **the source changed** — `transfer` rewrites the description when the parsed-content hash moves,
  and the write resets the AI stamps, so the enrichments have to run again.
- **the catalogue changed** — a curator rewriting a subject label changes the label-set hash, so the
  affected tags return to the `macro-category` queue, and adding, renaming or retiring a typology does
  the same for the descriptions: the typology identity signs the active label set, and the stamp is
  the only gate on the answer side, so a description that already carries a typology comes back when
  the catalogue moves. A run that then declines **clears** the answer it found — an answer another
  producer wrote does not survive a refusal from this one, or raising the floor would re-run the
  collection and change no label. The quality validator's reasons depend on the catalog too, which is
  the case `force` exists for.
- **`force=true`** — `embedding`, `macro-category`, `ner`, `quality-validator`, `thumbnail` and
  `typology` accept it and ignore their own stamp; `macro-category` still never touches a tag that
  already has a category, while `typology` re-reads a description that already carries one, because
  the stamp is what decides and not the answer.
  It is the way back from a reason a hash cannot see — an edited synonym rule, a curated exclusion,
  a prompt — and from a failure mark: the units it processes are stamped with the current producer,
  which clears the `ERROR`. For `thumbnail` it also means the documents marked `thumbnail_failed`
  come back, which is the way out of a bucket that was down during a run: the mark exists to stop a
  dead link from looping, not to make an outage permanent. A forced run advances by cursor, so it
  ends; `--limit N` bounds it further.

```bash
uv run python -m scrinalia.domains.archive.workers.runner embedding --option force=true
uv run python -m scrinalia.domains.archive.workers.runner typology --option force=true --limit 200
uv run python -m scrinalia.domains.archive.workers.runner quality-validator --option force=true
uv run python -m scrinalia.domains.archive.workers.runner thumbnail --option force=true
```

!!! warning "The reprocessing window closes at the first human-approved record"
    `HUMAN_APPROVED` is the shield: `ai_writable_documents()` excludes it, and `cleaning`, `ner`,
    `typology`, `thumbnail` and `quality-validator` all filter by it — `force` included, which is
    why a forced run re-reads every *ai-writable* document and not every document. `transfer` refuses
    to overwrite an approved description even when the source hash changed. The two documented
    exceptions are the derived work — `embedding`, which re-embeds a changed text, and
    `macro-category`, whose unit is the tag and whose queue is "no category yet", so a curator's
    category is never rewritten.

There is **no route and no flag that clears a stamp** for the workers that do not accept `force`
(`transfer`, `cleaning`, `conflict-judge`): to put a single document back in the queue there, you
have to remove that key from its `execution_log` in the database. Treat that as a repair, not as
routine operation.

## Interrupted runs

A run is `RUNNING` under a lease. The runner renews it every `--heartbeat-seconds`; when the lease
expires — the runner died, or its heartbeat stopped — the next runner (or the next CLI, which has the
same lease) marks the row `INTERRUPTED`, with a `finished_at` and the error text "O runner parou de
enviar sinal antes do fim desta execução." The API's boot repairs nothing, so several API processes
are safe. The sweep only touches the expired rows: a live claim of a sibling is never closed.

A scheduled `INTERRUPTED` run is retried by the scheduler (see [Scheduling and retries](#scheduling-and-retries)); a manual or CLI run is not. For the manual case, after an `INTERRUPTED` run:

1. Read `GET /api/v1/system/runs?status=INTERRUPTED` (or the panel) and open the error of the row.
2. Fix the cause — a missing Ollama model, an unreachable bucket, a database that was down.
3. Trigger the worker again. The per-unit stamps are what make this safe: the new run reads only
   what the interrupted one did not finish.

A queued run with no runner online waits, and the panel says so; [Cancelling a run](#cancelling-a-run)
is the way out. The retry policy is #43 and is described under
[Scheduling and retries](#scheduling-and-retries).

## Cancelling a run

`POST /api/v1/system/runs/{run_id}/cancel` (`OPERATE`) stops one execution (#72). The route answers
two outcomes, and the difference is the one the ledger's state machine draws:

- a `QUEUED` row **no runner has claimed** (`runner_id IS NULL`) never started and nothing is writing,
  so it closes `CANCELLED` immediately and frees the worker's slot;
- a row **in flight** only receives the request: `cancel_requested_at` and `cancel_requested_by` are
  written, the status stays `QUEUED`/`RUNNING`, and `uq_worker_run_active` keeps the slot. The worker
  consults the request once per batch, commits the batch it has already started, and the runner closes
  the row `CANCELLED` — with no `error`, because a deliberate stop is not a failure the grouped
  failures screen should present as a root cause.

The request is idempotent: a second click answers the same outcome and keeps the first author and
instant. A run that already reached a terminal state answers `409`, and an unknown id answers `404`.
The SPA offers the action on an active row of the *Execuções* tab of `/sistema/workers`, with the
confirmation the other destructive actions use; a requested stop is shown as a note while the row is
still running.

The honest limit is one batch (`db_batch_size`, 64 by default): `ThreadPoolExecutor` cannot kill a
thread and a torch forward pass cannot be interrupted, so `future.cancel()` only covers the queued
case. A `QUEUED` row is cancellable at once; a `RUNNING` one cooperates, and how long that takes is the
duration of the batch it is in — minutes when the quality validator calls the LLM per document.

`SIGINT`/`SIGTERM` give the CLI the same ending: the first signal sets the same request (the process
half of it), the worker stops at the next batch boundary and the run closes `CANCELLED`; a second
signal forces the exit. The daemon is deliberately different: it stops claiming on `SIGTERM` and
leaves its in-flight rows to the lease, so a runner that is being restarted reports `INTERRUPTED` — an
accident — not `CANCELLED` — a decision.

A `CANCELLED` run is never retried. The check is one function (`RunControl.checkpoint`) consulted once
per batch by every worker that loops, and
`testing/unit/archive/workers/test_worker_cancellation_gate.py` walks the catalogue and fails when a
looping worker stops consulting it.

## Scheduling and retries

The scheduler is a process of its own (ADR 0015):
`python -m scrinalia.domains.archive.workers.scheduler`. It takes `pg_try_advisory_lock` for its
lifetime — a second instance stands by — and ticks every 30 s (`--tick-seconds`). Each due schedule is
processed in one transaction with `FOR UPDATE SKIP LOCKED`: if the worker already has a
`QUEUED`/`RUNNING` row the period is skipped (`last_skipped_at` is written), otherwise the run is
enqueued with `trigger=SCHEDULE` and `attempt=1`, and `next_run_at` advances to the next future
occurrence. A scheduler that was down for several periods creates **one** catch-up run, not a replay.

The agenda is one row per worker (`archive_worker_schedules`): a five-field cron
(`minute hour day-of-month month day-of-week`), an IANA zone, the enabled state and the pinned
request. It is written on `/configuracoes/workers` (the Agenda section) and read on
`/sistema/workers`; `DEFAULT_TIMEZONE` is the instance's zone and the form's default. A disabled
agenda stores no next run; turning it back on recomputes it from the cron. The cron is evaluated in
the schedule's zone, never the server's: the spring-forward gap runs at the next valid instant, and the
repeated wall time on the fall-back day runs once.

The **origins** have their agenda on the origin row (`ingestion_origins.cron`/`timezone`) and are
written on `/sistema/ingestao`, not on the worker settings screen. A due origin enqueues one
`ingestion` run with `origin_code`; the slot is one per origin (`uq_worker_run_active` includes
`COALESCE(origin_code, '')`), so one origin's crawl does not wait behind another's, while the archive
workers keep one slot per worker. A period that arrives while that origin is running is skipped and
`last_skipped_at` is written; a failed scheduled ingestion is retried by the same policy as a worker.

A scheduled run that ends `FAILED` or `INTERRUPTED` is retried by the scheduler as a **new ledger row**:
`attempt = previous + 1`, `retry_of` the failed row, the same request, and a `not_before`
`60 s x 2^(attempt-1)` later, ±20% jitter, capped at 30 minutes. Three attempts in total; the third
failure is final. A manual or CLI run is never retried. The retry row is created immediately and waits
in the slot — the claim only takes a row whose `not_before` has passed — so a manual run of the same
worker answers `409` until it starts. A `CANCELLED` run is never retried: only `FAILED` and
`INTERRUPTED` scheduled runs are (ADR 0014 decision 9).

Two warnings that survive the scheduler:

- **A schedule can fire while a run is active.** The period is skipped, not queued: the queue is one
  slot per worker, and the panel shows the last skipped time. A missed period is one catch-up, never a
  replay.
- **Concurrency is refused by the database, not by a lock.** The partial unique index rejects the
  second in-flight run of the same worker; the API answers `409` and the CLI raises the same
  refusal. Nothing in the process serialises the calls, so the guard holds across processes, across
  a reload, and even when the CLI and the panel disagree about who is in charge. Triggering a
  *different* worker is accepted even while one is running — the row is queued and a runner claims
  it when it has a free slot — because the index limits one run per worker; the runner's
  `--concurrency` decides how many it executes at once.

The API route is a mutation, so it also needs an authenticated `ADMIN` session and a same-origin
`Origin` header. An external cron remains a supported way to run one-off work, through the CLI or the
route, but it is no longer the built-in answer: the agenda owns the next run, the skip and the
catch-up.

## Reading the failures

`GET /api/v1/system/failures` groups **both** error ledgers by the same key: the generated
`error_fingerprint` column, computed by PostgreSQL from the error text in `archive_worker_runs` and
in `archive_api_errors`. One root cause that broke a worker execution and an HTTP request appears
once, with `sources` (`WORKER`, `API` or both) saying where it was seen.

| Field | Meaning |
| --- | --- |
| `fingerprint` | the group's identity and the filter that leads back to the occurrences |
| `sample` | the most recent occurrence, unnormalized — the fingerprint reads like a key, not like a sentence |
| `occurrences` | how many times it happened in the window |
| `first_seen`, `last_seen` | the window inside which it happened |
| `sources` | which ledger(s) it came from |
| `worker_names` | the workers it broke, when any |
| `last_path`, `last_request_id` | the route and the request reference of the latest **API** occurrence of the group |

`total` in the response is the number of **groups** in the window, not a sum of occurrences. There
is deliberately **no grand total** across groups: a worker execution and an HTTP request are
different units, and adding them would produce a number nobody can act on.

The two details that make it readable:

- `last_path`/`last_request_id` are read from the latest **API** occurrence of the group, not from
  the latest occurrence of any kind. A mixed group whose newest row is a worker run still has a
  route and a request id worth showing.
- The `worker` filter narrows the **rows**, not the groups. A group that also broke the API keeps
  only its worker occurrences, which is what "this worker failed" means; an API-only group drops out.

`last_request_id` is the seam with the log: the same value is in the `ui_stream.jsonl` record of the
request, so a group leads to the traceback.

## Logs

Logging is configured from two settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `LOG_DIR` | `logs` | the directory the file sinks are written to |
| `LOG_LEVEL` | `INFO` | the level of the console sink and of the structured stream |

Three sinks are installed:

- the terminal, at `LOG_LEVEL`;
- `logs/critical.log`, at `ERROR`, rotated at 10 MB and kept 30 days — the post-mortem file;
- `logs/ui_stream.jsonl`, at `LOG_LEVEL`, serialized JSON, rotated at 50 MB and kept 7 days — the
  structured stream that carries the request id of every record.

Every request leaves with an `X-Request-ID`: the one the client sent (accepted only when it is at
most 64 characters of `[A-Za-z0-9._:-]`) or a generated one. It is echoed in the response header and
bound to the log context, so every record written while that request was served carries it —
including the one the unhandled-exception handler writes. The SPA shows it as "referência" next to
an error.

The access line is written by the same middleware, not by uvicorn, because uvicorn's record has no
request id:

```text
↔️ GET /api/v1/system/workers -> 200 em 1842.3 ms
❌ POST /api/v1/system/workers/ner/runs -> 500 em 12.4 ms
```

A `5xx` is a warning, everything else is an info line. The two orchestrator probes (`/health/live`
and `/health/ready`) are excluded from the access line — an orchestrator asks every few seconds and
would rotate a 50 MB file with nothing but "200 OK" — but they are not excluded from correlation.

## Recovering access

Password recovery is guided by the administrator, and which door applies is the only question:

- **Somebody forgot the password, and an administrator can sign in.** The administrator opens
  *Configurações → Usuários*, finds the account and uses **redefinir senha** — a button on the
  account's own row, so the reset is reached without expanding the card. The password typed there is
  **temporary**: the account replaces it at the next sign-in. The reset also **ends every session of
  that account** and **lifts a lockout**, which is the one case the screen alone can fix. It has no
  undo.
- **No administrator can sign in** — the last active one is locked out, deactivated or gone. Then
  the operation that would fix it is the thing nobody can reach, and the way in is the host's
  terminal:

```bash
# Which accounts exist, and which one is active. The address is what the commands below take.
uv run python -m scrinalia.domains.identity.cli list

# An explicit password. It is set as given; the account is not forced to replace it at the next sign-in.
uv run python -m scrinalia.domains.identity.cli reset-password --email pessoa@instituicao.org --password 'a nova senha'

# Without --password it generates one, prints it once and marks the account temporary.
uv run python -m scrinalia.domains.identity.cli reset-password --email pessoa@instituicao.org

# A deactivated account is reactivated before it can sign in again.
uv run python -m scrinalia.domains.identity.cli activate --email pessoa@instituicao.org
```

The CLI runs on the host against the same database and calls **the same service** the API calls, so
the password policy, the session revocation, and the last-administrator guard behind `deactivate` and
`set-role` are the same code and not a second implementation with fewer checks. It is also how the
first administrator is created ([Installation and deployment](install.md)).

Two things deliberately do not exist, and the sign-in screen says so rather than pretending
otherwise: there is **no e-mail reset** (nothing configures SMTP, and ADR 0009 keeps self-service
recovery out of scope), and there is **no reset-token table** to store, expire or leak. The screen's
*Esqueci minha senha* states these two paths and promises no message.

## Measuring the collection

Two tables answer two different questions, and a number taken from the wrong one misleads.

`execution_log` says **whether a worker ran over a unit**: it is the stamp the queue is built from.
`archive_worker_runs` says **what ran, when, with which engine and preset, over which options, how
long it took and how it ended** (`SUCCESS`, `FAILED`, `INTERRUPTED`, `CANCELLED`). An empty stamp count is a fact about the queue; the row
in the ledger is the fact about the execution that explains it — a stage at zero and one interrupted
run at start-up are the same event seen from two tables.

This is the query the reference collection was measured with. Run it against the installation's own
database, and treat every number as a measurement with a date rather than as a constant:

```bash
docker exec <container> psql -U <user> -d <database> -t -A -F' | ' -c "
SELECT 'descrições', count(*)::text FROM archive_documents
UNION ALL SELECT 'com pai', count(*)::text FROM archive_documents WHERE parent_id IS NOT NULL
UNION ALL SELECT 'sem nível', count(*)::text FROM archive_documents WHERE level_id IS NULL
UNION ALL SELECT 'tags', count(*)::text FROM archive_tags
UNION ALL SELECT 'tags sem categoria', count(*)::text FROM archive_tags WHERE macro_category_id IS NULL
UNION ALL SELECT 'propostas sugeridas', count(*)::text FROM archive_tag_merge_proposals WHERE status='SUGGESTED'
UNION ALL SELECT 'propostas aplicadas', count(*)::text FROM archive_tag_merge_proposals WHERE status='APPLIED'
UNION ALL SELECT 'rungs decididos', count(*)::text FROM archive_hierarchy_node_plans WHERE status <> 'SUGGESTED'
UNION ALL SELECT 'rungs no total', count(*)::text FROM archive_hierarchy_node_plans
UNION ALL SELECT 'ner_v2', count(*)::text FROM archive_documents WHERE execution_log ? 'worker_ner_v2'
UNION ALL SELECT 'typology_v2', count(*)::text FROM archive_documents WHERE execution_log ? 'worker_typology_classifier_v2'
UNION ALL SELECT 'macro_v1 (tags)', count(*)::text FROM archive_tags WHERE execution_log ? 'worker_macro_category_v1'
UNION ALL SELECT 'embedding_v1', count(*)::text FROM archive_documents WHERE execution_log ? 'worker_embedding_v1'
UNION ALL SELECT 'quality_validator_v1', count(*)::text FROM archive_documents WHERE execution_log ? 'worker_quality_validator_v1'
UNION ALL SELECT 'publicados', count(*)::text FROM archive_documents WHERE is_published
UNION ALL SELECT 'revisões humanas', count(*)::text FROM archive_document_revisions;"
```

One trap is worth knowing before reading those numbers: `?` says the key **exists**, not that it is
current. Since the identity-keyed stamps carry the producer, a document stamped by another model, by
an older dependency or by another threshold counts here and is still pending for the configuration in
the code — the `pending` column of the panel and the queue preview are what answer *that* question.
The raw counts are good for "did this worker ever run over this collection".

## The documentation site

These guides are published at <https://cassiodalla.github.io/Scrinalia/> — English at the root,
Portuguese under `/pt/` — and **CI publishes them; no person does.** The `docs` job builds the site
with `mkdocs build --strict` on a full-history checkout (the freshness report is a report *against
git*, ADR 0010), uploads `site/` as the Pages artifact, and the `docs-publish` job deploys exactly
that artifact. The decision, and the alternatives it rejected, are in
[ADR 0012](../adr/0012-the-documentation-site-is-published-by-ci.md).

Three consequences are worth knowing before touching a workflow or the theme:

- **Only a push to `main` publishes.** A merge into `dev` builds the site and publishes nothing: the
  site is the documentation of the **release**, and `main` is the branch that moves at a release.
  The `github-pages` environment trusts `main` — and the `gh-pages` branch the old manual build used
  — so a deploy from `dev` would need that policy changed first.
- **Re-running the workflow run is the recovery.** The deploy takes the artifact the same run built,
  so a transient failure is fixed with "re-run jobs". There is no `mkdocs gh-deploy` step and
  `gh-pages` is not the source of the site any more: publishing by hand is no longer a path, which is
  what stops the published site from being a release older than the tag.
- **The theme is the system's identity**, and it lives in two places that are pinned to each other:
  `docs/assets/` (the mark, the favicon, the self-hosted PT Serif with its licence) and
  `docs/assets/stylesheets/scrinalia.css`, which carries the tokens of
  `apps/curator/src/styles.css`. `testing/unit/docs/test_docs_brand.py` fails when an asset
  `mkdocs.yml` names is missing — `--strict` does **not** catch that — or when a copy drifts from the
  curator's own file.

## Known limits and accepted trade-offs

These are measured, accepted, and not waiting for a fix. They are here so that an operator knows which
behaviour to expect, and so that a limit already paid for is not read as a defect.

- **Nobody is paged.** Observability is the panel, the run ledger and the failure groups; an external
  alerting service is deliberately not part of the system (ADR 0005). A new root cause is found by
  somebody opening the screen, not by a notification.
- **The runner reaches the database.** A runner on another machine needs a private path to
  PostgreSQL and a credential; the API's `DB_*` can stay local (ADR 0014). The optional
  least-privilege role and the tunnel are in the [install guide](install.md#the-network-and-the-credential).
- **The lease is not a fencing token.** A runner that lost its lease can still write the archive
  until its worker stops; the stamps make the re-run idempotent and the ledger row is fenced, but a
  duplicate execution after a lease expiry is possible. A hard fence is future work.
- **The queue is one slot per worker.** A second run for a worker with one in flight answers `409`,
  and a schedule has to coalesce; a backlog or a priority is not what this queue is.
- **The retry is bounded and unclassified.** A scheduled failure spends up to three attempts,
  whatever the cause: a missing model costs three bounded attempts, because a classifier that is
  wrong in the other direction either wastes the GPU or hides a real failure. The retry holds the
  worker's slot during the backoff.
- **One scheduler, one lock.** The advisory lock releases when the connection dies and a standby
  takes over within its retry interval; there is still a window of one tick with no scheduler.
- **A cancellation stops at the batch boundary.** A `QUEUED` run no runner claimed closes at once; a
  `RUNNING` one keeps its slot until it finishes the current batch, so stopping a quality-validator run
  that calls the LLM per document can take minutes. A hard kill is not a cancellation: the process
  death is `INTERRUPTED` when the lease expires.
- **The arrangement `path` is not enforced by the database.** The column is materialised by the
  service, so a hand-written `UPDATE` can diverge it from the tree; the `PATH_DIVERGENCE` diagnostic
  is what finds it. Do not write `path` directly — go through the routes that own the move.
- **Authentication has conscious limits.** The login rate limiter is **process-local** and resets on
  restart, which is why the durable defence is the per-account lockout column; revoking a session
  records that it was revoked, not **who** revoked it; and OIDC/SSO, second factors and e-mail
  recovery are out of scope (ADR 0009). Recovery is the administrator or the CLI on the host (see
  [Recovering access](#recovering-access)).
  **The first account is a window.** While `auth_users` is empty, `POST /api/v1/setup/admin` is
  public and whoever reaches the instance first may create the administrator; the table lock makes
  two simultaneous attempts safe, and nothing makes the window safe (ADR 0011). Configure the
  instance before exposing it, and read `GET /api/v1/setup/status` — `{"needs_setup": true}` on a
  reachable instance is an invitation.
- **The contract does not declare the session cookie.** The OpenAPI document carries no `security`
  scheme for it, because a global requirement would also mark the diffusion routes and the health
  probes as protected (ADR 0009). A generated client cannot discover the requirement; it answers 401
  like any other anonymous request.
- **The ranking depends on the mode, and that is a decision the archivist makes.** A semantic search
  that **finds more** is not a search that **orders better**: the full-text ranking wins when the term
  is exact, the semantic one when the subject is known but the vocabulary of the fonds is not, and the
  hybrid mode fuses the two so the choice is not required. The three modes and when to prefer each one
  are in the curation guide, and `testing/evaluation/retrieval_modes.py` measures them per query
  stratum.
