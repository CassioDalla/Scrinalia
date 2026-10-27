# ADR 0016: The origin is a first-class object

- **Status:** Accepted
- **Date:** 2026-10-25
- **Applies to:** the commits that added `ingestion_origins`, the origin columns on the pipeline
  layers and the run ledger, the `ingestion` stage in the scheduler/runner/panel, and the manual
  origin (#44).

## Context

ADR 0008 made the origin a **parameter**: `SourceConfig` carries where the adapter goes,
`SourceSchema` carries which of the site's labels fills which staging column, and `ACERVO_SOURCE`
selects both. That was the right first step, and it left three gaps that only become visible when a
second origin exists:

1. **There is one selector, not a lifecycle.** `ACERVO_SOURCE` names one code for the process. It has
   no enabled/paused state, no URLs an operator can change from the screen, and no agenda.
2. **The pipeline does not carry the origin.** `scraping_queue`, `raw_data`, `staging_documents`,
   `archive_documents` and `archive_worker_runs` have no `origin_code`, so the panel can answer
   "what is in the transfer queue" and never "which origin is this queue".
3. **The transform receives one schema per run.** `run_staging_pipeline` applied one
   `SourceSchema` to every record. A run that read two origins would have to be two runs, and a
   second origin's vocabulary would be an edit to the shared transform — the boundary ADR 0008
   exists to protect.

The ingestion was also the only stage outside the operations panel: a host CLI with no ledger, no
lease and no schedule. #49 needs the origin axis before it can surface the queue, and #44 needs the
origin to exist before either can happen.

## Decision

### 1. An origin is a definition in code plus a row in the database

`domains/ingestion/origin_registry.py` holds the **cheap** definition: code, label, kind, the
Pydantic model of the configuration and the metadata the screen renders. `domains/ingestion/origins.py`
holds the **runtime**: the `SourceSchema` next to its adapter and the ports the job receives. The two
are split so the API process can list origins without importing `requests`/`bs4`.

`ingestion_origins` is the lifecycle: `enabled`, `config` (URLs, path, delay), `options` (the run
policy a scheduled execution inherits), `cron`, `timezone`, `next_run_at`, the `last_*` facts and the
author of the last change. Adding an origin is a module with its adapter and schema, an entry in the
registry and a row — the transform, the job and the screen do not change.

The `config_fields` the screen renders are metadata *about* the origin's own Pydantic model; a test
pins the two sets equal, so a URL cannot become a JSON box nobody knows how to fill.

### 2. `origin_code` is provenance, not identity

The queue, the raw payload, the staging record, the archive description and the run ledger carry
`origin_code`. The **business key stays `description_id`**: an origin is where the record came from,
not part of what the record is, and making `(origin_code, description_id)` the key would touch every
foreign key and the archive's primary key for a collision no shipped origin produces. An adapter that
can collide namespaces its own ids (`manual-<uuid>`; a CSV adapter would prefix its rows).

The staging transform resolves the `SourceSchema` **per record**, from the record's own origin. There
is still no default: a record whose origin the deployment never declared fails that record instead
of inheriting the reference site's labels. The provenance is deliberately **excluded from
`StagingRecord.parsed_content_hash()`**: the CDC key is what the parser read, and folding the origin
into it would re-transfer the whole collection once for a column no AI worker writes.

### 3. The ingestion is the stage in front of the archive, in the same ledger

`ingestion` is a `WorkerSpec` ordered before `transfer`, with `unit="origin"`, no engine and no stamp.
It runs in the **same** `archive_worker_runs` ledger, the same runner, the same lease and the same
cancellation as the AI workers, because those are the properties the panel already promises. A run
of it has `worker_name="ingestion"` and its `origin_code` set; the archive workers keep
`origin_code IS NULL` because they span the collection and have no single source to name.

`uq_worker_run_active` becomes `(worker_name, COALESCE(origin_code, ''))` with the same
`status IN ('QUEUED','RUNNING')` predicate: the archive workers keep their one-slot-per-worker guard,
and each origin gets a slot of its own. The scheduler reads the due origins and enqueues one
`ingestion` run per origin; a period that arrives while that origin already has an active run is
skipped, and a failed scheduled run is retried with the existing policy.

The API only enqueues. The dedicated origin routes (`/api/v1/ingestion/origins/...`) are the
selector: the generic worker route refuses `ingestion` because it has no origin to name.

### 4. The manual entry is an origin, not an approval

`manual` is a normal origin with a `SourceSchema` whose keys are the form's ISAD(G) fields. The
submit writes `raw_data`, a `scraping_queue` row marked `DONE` (the form is the discovery), and the
staging record; then it enqueues the `transfer` worker. The archive description is born
`PENDING_AI`, and the AI queues see it. The submit does **not** write `HUMAN_APPROVED`: the form is
data entry, not review, and a review that skipped AI would be the opposite of the guarantee. The
archivist approves in the dossier after the AI runs.

`raw_data.created_by` and `created_by_user_id` record who typed the record. A duplicate
`description_id` is refused before the write; the form generates a `manual-<uuid>` id so a retried
submit is the same record.

### 5. The CSV import is deferred

The second adapter that proves the boundary in this change is the **manual origin**: it has its own
schema, its own port shape (none) and runs end to end into the same staging columns. The CSV import
— parsed in the browser and sent as JSON rows, with no object storage — is #191 and depends on this
origin table; it must not grow this change.

### 6. Per-origin AI configuration is not in this change

The issue says "perhaps the preset". Applying a preset per origin requires partitioning the AI
queues and the stamp identity by origin and a second precedence for the worker settings. The
`origin_code` column is the foundation; the decision is a separate issue.

## Rationale

- **The owner decides the lifecycle.** An origin's URLs, its enabled state and its agenda are
  operational facts an institution changes without a deploy. The labels are still the site's and stay
  next to the adapter.
- **One ledger is the panel's promise.** A second ledger for ingestion would duplicate the claim,
  the lease, the retry, the cancellation and the failure fingerprint, and the panel would have to
  reconcile two "in flight" answers.
- **The slot is the database's.** `COALESCE` in the partial index gives each origin a slot without a
  process lock, and keeps the archive workers' existing guarantee byte for byte.
- **A manual entry is not a review.** The most consequential default in the system is whether an AI
  may touch a record. A form is not a person reading the AI's output; the review stays where the
  evidence and the revision ledger are.

## Consequences

Positive:

- Adding an origin is a module, a registry entry and a row; the transform learns no site.
- The panel can answer "which origin is this queue", and the ledger can attribute an ingestion run
  to the source it processed.
- The ingestion has a lease, a schedule, a retry and a cancellation for free; an operator sees it in
  the same execution ledger as the AI workers (`/sistema/workers`, the *Execuções* tab).
- A manual record follows the same path as a scraped one and is visible to the AI queues, with the
  author on the raw row.

Negative, accepted:

- **The origin is not part of the archive key.** Two origins that emit the same `description_id` are
  the same record; the adapter must namespace. A composite key remains a larger decision.
- **The legacy rows are attributed to the reference origin.** The migration backfills `pmc`; a
  deployment that ran another origin corrects the rows, because the alternative (reading
  `ACERVO_SOURCE` at migration time) would make the migration depend on a variable that is gone.
- **The manual form ships the essential fields.** The rest of `StagingDocumentDTO` is #192, and the
  CSV import is #191.
- **The slot is one per origin, not a backlog.** A second click while an origin runs is a 409; the
  scheduler's period is skipped, not queued, like the AI workers (ADR 0014/0015).

## Alternatives considered

- **A separate ingestion ledger and scheduler.** Cleaner domain separation, rejected because it
  duplicates the claim/lease/retry/cancellation and the panel's "in flight" answer; the existing
  ledger is already about an execution, not about a worker.
- **The manual form writes directly to `archive_documents` as `HUMAN_APPROVED`.** Shortest path,
  rejected: it loses `raw_data`/`staging`/the parsed-content hash and the AI never touches the
  record. It is the opposite of the guarantee the form is supposed to make.
- **An external cron plus the CLI, no ledger.** Rejected: no lifecycle, no agenda, no attribution and
  no panel; the issue's own definition of done asks for all three.
- **A composite `(origin_code, description_id)` key.** Rejected for this change: it touches every
  reader, the archive's primary key and the hierarchy self-reference. Revisit if a real origin
  collision appears.
- **Per-origin AI presets now.** Deferred, not rejected: it needs a partitioned queue and a stamp
  identity per origin, which is a different decision with its own measurement.

## Revisit trigger

Reconsider if any of these becomes true:

- an origin needs a key of its own because two origins really emit the same `description_id`;
- a second origin needs a different AI preset or a different set of text columns, making the global
  worker settings insufficient;
- the ingestion needs more than one active run per origin (a backlog), or priority between origins;
- the CSV import needs a stored file rather than the browser-parsed rows of #191.
