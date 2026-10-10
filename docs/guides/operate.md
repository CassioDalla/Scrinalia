---
sources:
  - src/scrinalia/domains/archive/workers/catalogue.py
  - src/scrinalia/domains/archive/workers/runner.py
  - src/scrinalia/domains/archive/workers/configuration.py
  - src/scrinalia/domains/archive/workers/ledger.py
  - src/scrinalia/domains/archive/workers/worker_*.py
  - src/scrinalia/domains/archive/worker_stamp.py
  - src/scrinalia/domains/archive/models/operations.py
  - src/scrinalia/domains/archive/models/enums.py
  - src/scrinalia/domains/archive/schemas/system_schema.py
  - src/scrinalia/domains/archive/repository/worker_run_repo.py
  - src/scrinalia/domains/archive/repository/worker_settings_repo.py
  - src/scrinalia/domains/archive/repository/worker_stamp_repo.py
  - src/scrinalia/domains/archive/repository/governance.py
  - src/scrinalia/domains/archive/repository/failure_repo.py
  - src/scrinalia/domains/archive/services/worker_operations_service.py
  - src/scrinalia/domains/archive/services/worker_run_service.py
  - src/scrinalia/domains/archive/services/failure_service.py
  - src/scrinalia/api/controllers/system_controller.py
  - src/scrinalia/api/controllers/health_controller.py
  - src/scrinalia/api/controllers/setup_controller.py
  - src/scrinalia/api/worker_runtime.py
  - src/scrinalia/api/lifespan.py
  - src/scrinalia/api/middleware.py
  - src/scrinalia/api/system_health.py
  - src/scrinalia/core/logger.py
  - src/scrinalia/core/config.py
  - src/scrinalia/domains/identity/cli.py
  - src/scrinalia/domains/identity/services/auth_service.py
  - src/scrinalia/api/controllers/users_controller.py
  - docs/adr/0009-authentication-and-authorization.md
  - docs/adr/0011-first-run-setup-without-an-open-door.md
  - apps/curator/src/router.tsx
  - apps/curator/src/routes/SystemWorkersRoute.tsx
  - apps/curator/src/routes/SystemRunsRoute.tsx
  - apps/curator/src/routes/SystemHealthRoute.tsx
---

# Operations

This page is for whoever runs the machine day to day: which workers exist, in which order they
run, how to start one, how the effective configuration is resolved, what the operations panel
shows, and what to do when something breaks. Installing and configuring the system is in
[Installation and deployment](install.md); the archival decisions each screen takes are in
[Curation](curate.md).

## The workers and the pipeline order

`src/scrinalia/domains/archive/workers/catalogue.py` is the single definition of a worker: its
position in the pipeline, the unit its queue counts, whether it respects the review governance,
and the stamp it writes. The catalogue imports no worker — it resolves each module lazily — so
reading it is cheap.

Nine workers, in pipeline order:

| # | Name | Module | Unit | Governed | Effective engine from |
| --- | --- | --- | --- | --- | --- |
| 1 | `transfer` | `worker_archive_transfer` | staging record | no | — |
| 2 | `cleaning` | `worker_cleaning_regex` | document × active `REWRITE` rule | yes | — |
| 3 | `ner` | `worker_ner` | document | yes | signature |
| 4 | `typology` | `worker_typology` | document | yes | signature |
| 5 | `thumbnail` | `worker_thumbnail` | document | yes | — |
| 6 | `conflict-judge` | `worker_resolve_tag_entity_conflict` | tag × entity pair | no | signature |
| 7 | `macro-category` | `worker_macro_category` | tag | no | signature |
| 8 | `quality-validator` | `worker_quality_validator` | document | yes | active `LLM_CHECK` rule |
| 9 | `embedding` | `worker_embedding` | document | no | signature |

The order is the order in which the stages unblock each other, and it is the order the pipeline
section of the panel shows:

```text
transfer -> cleaning -> ner -> typology -> thumbnail -> conflict-judge -> macro-category -> quality-validator -> embedding
```

- **`transfer`** copies the structured staging record into the archive description, keyed on the
  hash of the parsed record (`staging_content_hash`). It is the only stage that rewrites content:
  when the hash changes, the written `execution_log` is reset and the AI enrichments have to run
  again. A document a human already approved is never overwritten, and a staging record with the
  same hash is not written at all.
- **`cleaning`** applies the active cleaning rules of kind `REWRITE`, one pass per rule. A rule of
  kind `VALIDATE` or `LLM_CHECK` never rewrites anything — flagging is the quality validator's job.
- **`ner`** extracts proper names, places and institutions from the composed document text.
- **`typology`** classifies each description against the active typology catalogue by zero-shot.
- **`thumbnail`** downloads the original image and stores a miniature in the object storage.
- **`conflict-judge`** compares the tag vocabulary with the entity vocabulary and asks the local
  LLM whether an ambiguous term is a subject or a proper name. Every verdict, auto-resolved or sent
  to a human, leaves a row in `archive_ai_review_queue`.
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
The panel never re-derives it. `pending` is how many units the next run would read; `processed` is
how many carry the worker's stamp; `failed` counts the stamps that record a failure (`ERROR`, or the
`thumbnail_failed` mark).

| Worker | What is pending | Idempotency stamp |
| --- | --- | --- |
| `transfer` | staging records with no archive row, or whose parsed-content hash differs from the archived one — except documents a human approved or rejected | none; a staging-record hash, plus `hierarchy_parent_v1` for a declared parent |
| `cleaning` | documents the active `REWRITE` rules have not stamped yet; a document pending for two rules counts twice | `cleaning_rule_{rule_id}` |
| `ner` | documents without the stamp that have text in at least one extracted column | `worker_ner_v2` |
| `typology` | documents with no typology and no stamp that have text | `worker_typology_classifier_v2` |
| `thumbnail` | documents with a source image, no storage URI and no failure mark — every marked one, with `force` | none; the `storage_thumbnail_uri` column, plus the `thumbnail_failed` mark |
| `conflict-judge` | **not measurable cheaply**: the queue is the trigram product of tags × entities, measured at 53 s on the real collection. The panel shows what was already judged | none; the `archive_ai_review_queue` row |
| `macro-category` | tags with no subject category whose stamp does not carry the current label set | `worker_macro_category_v1` (on the tag; value is the hash of the label set) |
| `quality-validator` | documents without the stamp, unless `force` is on | `worker_quality_validator_v1` |
| `embedding` | documents whose stamp differs from the MD5 of the effective text — the first run and every later text change | `worker_embedding_v1` (value is the MD5 of the embedded text) |

The `transfer` counter is the heaviest one: it validates the whole staging table through the same
port the transfer uses. It is read once per panel load and is not polled in a loop.

## Running a worker

### The unified runner

Prefer the unified runner, which exposes every worker behind one interface. Run it from the
repository root:

```bash
uv run python -m scrinalia.domains.archive.workers.runner <name> \
    [--engine X --preset Y --batch N --option key=value --by "who"]
```

For example:

```bash
# Classify the typology of every pending description, in batches of 100.
uv run python -m scrinalia.domains.archive.workers.runner typology \
    --engine deberta_typology --preset cpu_local --batch 100 --by "ana"

# Force the embedding of every description, ignoring the text hash.
uv run python -m scrinalia.domains.archive.workers.runner embedding --option force=true

# Point the conflict judge at another Ollama host for this run only.
uv run python -m scrinalia.domains.archive.workers.runner conflict-judge \
    --option host=http://ollama.interno:11434 --by "ana"
```

| Flag | Meaning |
| --- | --- |
| `<name>` | one of the nine names above; any other value is refused with the list of options |
| `--engine X` | a registered engine of the worker's axis, e.g. `spacy_ner`, `deberta_typology`, `ollama_judge` |
| `--preset Y` | a preset of that axis, e.g. `gpu`, `lemmatizer`, `cpu_local`, `gpu_cloud`, `granite_local`, `multilingual_minilm` |
| `--batch N` | batch size per transaction, forwarded to the workers that declare `db_batch_size` |
| `--option key=value` | an extra parameter, repeatable; `key` without `=` is refused |
| `--by "who"` | free text naming who is running it; the CLI runs on the host and has no session, so this stays a name with no account behind it |

`--option` coerces exactly two values: `true` and `false` become booleans. Every other value stays a
string, so an option that expects a number or a list is not settable from the command line. The flag
is validated against the worker's `execute` signature: an option the worker does not declare is
refused, unless the worker ends with `**engine_kwargs`, which is the documented way to override
`device`, `host` and similar engine parameters for one run.

Two things are always refused:

- `config` is refused because it is a runner dataclass (`NerRunnerConfig` and its siblings), not a
  value a command line or a JSON body can carry; a dictionary reaching `execute` would fail with an
  attribute error instead of a sentence. Pass the individual fields instead.
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

## The operations panel

The panel is the `/api/v1/system/*` surface and the three cards of `/configuracoes`, under *Operação*,
in the SPA: the menu no longer carries them (issue #22).

| Route | Method | Permission | What it does |
| --- | --- | --- | --- |
| `/api/v1/system/workers` | `GET` | authenticated | the nine workers with configuration, queue numbers and last/active run, in one request |
| `/api/v1/system/workers/{worker_name}/runs` | `POST` | `OPERATE` | queues one run with per-run overrides and answers `201` immediately |
| `/api/v1/system/workers/{worker_name}/settings` | `PUT` | `OPERATE` | persists the default engine/preset/batch/options |
| `/api/v1/system/workers/{worker_name}/settings` | `DELETE` | `OPERATE` | drops the override so the worker follows the code |
| `/api/v1/system/workers/{worker_name}/settings/revisions` | `GET` | authenticated | who changed what, when |
| `/api/v1/system/runs` | `GET` | authenticated | the execution ledger, newest first; filters `worker`, `status`, `fingerprint`, `limit`, `offset` |
| `/api/v1/system/failures` | `GET` | authenticated | the grouped root causes; filters `days` (default 30), `worker`, `limit` |
| `/api/v1/system/health` | `GET` | `OPERATE` | database, Ollama models, object storage and the process |

Only `ADMIN` carries `OPERATE`; `CURATOR` and `VIEWER` can read the workers, the ledger and the
failures, but cannot trigger a run or change a default.

The SPA mirrors it, as cards of `/configuracoes` under *Operação*:

| Screen | Shows |
| --- | --- |
| `/sistema/workers` | the nine workers: engine, preset and model, the queue, the persisted default and a run button |
| `/sistema/execucoes` | the execution ledger, and the failures of the last 30 days grouped by root cause; clicking a cause filters the ledger to its occurrences |
| `/sistema/diagnostico` | database, Ollama models, thumbnail storage and the effective process configuration |

The screen only polls while something is running, because the `transfer` counter makes one
`/system/workers` call cost about two seconds on the real collection.

### Health: three endpoints, three questions

They are not interchangeable, and merging them is the mistake to avoid.

| Endpoint | Question | Behaviour |
| --- | --- | --- |
| `GET /health/live` | is the process alive? | touches nothing, always `200` while the process answers; excluded from the OpenAPI document |
| `GET /health/ready` | may this instance receive traffic? | runs `SELECT 1`; `200`, or `503` when the database does not answer; also outside `/api/v1` and outside the contract |
| `GET /api/v1/system/health` | which piece is down? | the human panel: database counts, the Ollama models the presets require and which are missing, the object-storage bucket, and the effective process configuration — secrets as presence, never as value |

A liveness probe that consults the database would restart the API whenever the database restarts,
which is why `live` touches nothing. The readiness probe owns its own engine with a connection and a
statement timeout, so a probe against an unreachable host fails fast instead of hanging for the
operating system's TCP timeout.

## The run ledger

`archive_worker_runs` has one row per execution, for **both** the CLI and the panel: the ledger is
about the worker, not about the button that started it. A row carries `worker_name`, `status`,
`trigger` (`CLI` or `API`), `requested_by` (and `requested_by_user_id`), `engine_name`, `preset`,
the resolved `config`, `queued_at`, `started_at`, `finished_at`, `duration_ms`, `error` and the
generated `error_fingerprint`.

The statuses are `QUEUED`, `RUNNING`, `SUCCESS`, `FAILED` and `INTERRUPTED`. The `QUEUED` row is
committed through the ledger's **own session before** the executor thread receives its id; a row
still inside the request's transaction would be invisible to that thread and the run would sit at
`QUEUED` forever.

`uq_worker_run_active` is a **partial unique index** on `(worker_name)` where the status is `QUEUED`
or `RUNNING`. It, and not a process lock, is the concurrency guard: at most one run per worker may
be in flight, across processes and across a reload. A second submission becomes an
`IntegrityError` that the API turns into `409` with a sentence ("Já existe uma execução em
andamento para o worker '…'"), and that the CLI surfaces the same way.

The panel's executor runs **one worker at a time** (`WORKER_RUNTIME_MAX_WORKERS`, default 1) because
the workers are CPU-bound — two torch models on the same CPU slow each other down without producing
more. It is **not a scheduler**: no retry, no cron, no priority. It exists so a person can press a
button.

## Reprocessing a document or a batch

Re-running a worker is safe and incremental: its queue is the absence of its stamp, so a second run
touches only what is still pending. What puts a unit back in the queue:

- **the text changed** — a human edit or an approved/edited/undone text excerpt. `embedding`
  re-queues by itself because its stamp *is* the MD5 of the effective text; the text-dependent
  stamps (`worker_ner_v2`, `worker_typology_classifier_v2`, `worker_quality_validator_v1`) are
  invalidated by the text-quality service.
- **the source changed** — `transfer` rewrites the description when the parsed-content hash moves,
  and the write resets the AI stamps, so the enrichments have to run again.
- **the catalogue changed** — a curator rewriting a subject label changes the label-set hash, so the
  affected tags return to the `macro-category` queue. The quality validator's reasons depend on the
  catalog too.
- **`force=true`** — `embedding`, `macro-category`, `thumbnail` and `quality-validator` accept it and
  ignore their own stamp; `macro-category` still never touches a tag that already has a category. For
  `thumbnail` it also means the documents marked `thumbnail_failed` come back, which is the way out
  of a bucket that was down during a run: the mark exists to stop a dead link from looping, not to
  make an outage permanent.

```bash
uv run python -m scrinalia.domains.archive.workers.runner embedding --option force=true
uv run python -m scrinalia.domains.archive.workers.runner quality-validator --option force=true
uv run python -m scrinalia.domains.archive.workers.runner thumbnail --option force=true
```

!!! warning "The reprocessing window closes at the first human-approved record"
    `HUMAN_APPROVED` is the shield: `ai_writable_documents()` excludes it, and `cleaning`, `ner`,
    `typology`, `thumbnail` and `quality-validator` all filter by it. `transfer` refuses to overwrite
    an approved description even when the source hash changed. The two documented exceptions are the
    derived work — `embedding`, which re-embeds a changed text, and `macro-category`, whose unit is
    the tag and whose queue is "no category yet", so a curator's category is never rewritten.

There is **no route and no flag that clears a stamp**: to put a single document back in the queue for
a worker that does not accept `force`, you have to remove that key from its `execution_log` in the
database. Treat that as a repair, not as routine operation.

## Interrupted runs

A run left at `QUEUED` or `RUNNING` by a process that died is worse than a wrong one: the partial
unique index would block that worker forever. At start-up, `api/lifespan.py` marks every such row as
`INTERRUPTED`, with a `finished_at` and the error text "O processo anterior terminou antes do fim
desta execução."

Nothing is retried automatically. After an `INTERRUPTED` run:

1. Read `GET /api/v1/system/runs?status=INTERRUPTED` (or the panel) and open the error of the row.
2. Fix the cause — a missing Ollama model, an unreachable bucket, a database that was down.
3. Trigger the worker again. The per-unit stamps are what make this safe: the new run reads only
   what the interrupted one did not finish.

The recovery assumes a **single API process**. With `uvicorn --workers > 1`, one process's start-up
would mark a sibling's live run as interrupted, so scaling out requires moving the executor (and the
recovery) out of the API first. The partial unique index stays valid either way.

## Scheduling

There is no scheduler today. Operationally, that means an external cron — or any orchestrator you
already run — has to hang off one of the two entry points:

```bash
# On the host, from the repository root.
uv run python -m scrinalia.domains.archive.workers.runner embedding --by "cron"

# Or through the API, which queues the run and returns immediately.
curl -sS -X POST "http://localhost:8000/api/v1/system/workers/embedding/runs" \
    -H "Content-Type: application/json" -H "Origin: http://localhost:8000" \
    -b "scrinalia_session=<cookie>" \
    -d '{"db_batch_size": 100}'
```

Two warnings that the design makes explicit:

- **A run may last longer than the cron interval.** The route answers `201` as soon as the run is
  queued, so the cron has no idea whether the previous run finished. Schedule on a period longer
  than a run, or read the ledger before triggering.
- **Concurrency is refused by the database, not by a lock.** The partial unique index rejects the
  second in-flight run of the same worker; the API answers `409` and the CLI raises the same
  refusal. Nothing in the process serialises the calls, so the guard holds across processes, across
  a reload, and even when the CLI and the panel disagree about who is in charge. Triggering a
  *different* worker is accepted even while one is running — it queues behind the others — because
  the index limits one run per worker; `WORKER_RUNTIME_MAX_WORKERS` decides how many the panel
  itself runs at once.

The API route is a mutation, so it also needs an authenticated `ADMIN` session and a same-origin
`Origin` header. A cron on a remote host is simpler through the CLI.

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

# An explicit password. The account is marked temporary, so it replaces it at the next sign-in.
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
`archive_worker_runs` says **what ran, when, with which engine and preset, how long it took and how it
ended** (`SUCCESS`, `FAILED`, `INTERRUPTED`). An empty stamp count is a fact about the queue; the row
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

One stamp carries a trap worth knowing before reading the number: `embedding_v1` is the **MD5 of the
effective text**, not the identity of the model, so it stays up to date when the vectors do not —
changing `torch`, `sentence-transformers` or the preset does not put a single description back in the
queue. When the embedding model changes, the vector has to be rebuilt explicitly.

## Known limits and accepted trade-offs

These are measured, accepted, and not waiting for a fix. They are here so that an operator knows which
behaviour to expect, and so that a limit already paid for is not read as a defect.

- **Nobody is paged.** Observability is the panel, the run ledger and the failure groups; an external
  alerting service is deliberately not part of the system (ADR 0005). A new root cause is found by
  somebody opening the screen, not by a notification.
- **The executor assumes a single API process.** The API runs one worker at a time
  (`WORKER_RUNTIME_MAX_WORKERS`) and the recovery in `api/lifespan.py` marks what a dead process left
  behind, which is only correct with `uvicorn --workers 1` (see [Interrupted runs](#interrupted-runs)).
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
- **Ranking by semantics alone is weaker than the lexical one.** The vectors work and the order does
  not: the bench that measures it is `testing/evaluation/retrieval_quality.py`, and combining the two
  rankings is open work. A semantic search that **finds more** is not a search that **orders better**.
