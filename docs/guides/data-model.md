---
sources:
  - src/scrinalia/domains/ingestion/models.py
  - src/scrinalia/domains/ingestion/origin_registry.py
  - src/scrinalia/domains/ingestion/origins.py
  - src/scrinalia/domains/diffusion/models.py
  - src/scrinalia/domains/diffusion/coverage.py
  - src/scrinalia/domains/diffusion/publication_repository.py
  - src/scrinalia/domains/diffusion/diffusion_registry.py
  - src/scrinalia/domains/staging/models.py
  - src/scrinalia/domains/archive/models/**
  - src/scrinalia/domains/identity/models/**
  - src/scrinalia/domains/archive/worker_stamp.py
  - src/scrinalia/domains/archive/repository/text_quality_repo.py
  - src/scrinalia/domains/archive/repository/tag_repo.py
  - src/scrinalia/api/schemas/public.py
  - src/scrinalia/core/language/__init__.py
  - migrations/versions/44a1b2c3d4e5_the_origin_is_a_first_class_object.py
  - migrations/versions/0b1c2d3e4f5a_add_the_diffusion_channels.py
  - migrations/versions/9f2a7c1e5b30_add_the_diffusion_publication_scopes.py
  - migrations/versions/a4c8d0e2f614_derive_the_channel_coverage_in_a_view.py
  - migrations/versions/b7e3f9a1c852_add_the_publication_batch_ledger.py
  - migrations/versions/c9e1f4b7d620_let_the_coverage_compose_the_exclusions_view.py
  - migrations/versions/b7e4c2a9f1d0_the_schedule_and_the_retry.py
  - migrations/versions/fe7fcab37207_add_the_failure_fingerprint_and_the_api_.py
  - testing/conftest.py
---

# Data model

This page is about what the data *means*: which layer owns which fact, what each table is for, and
which writes are decisions a person can undo. It is not an install guide — see
[Installation and deployment](install.md) for the schema lifecycle, [Operations](operate.md) for
running the workers and [Curation](curate.md) for the screens over these tables.

The schema is owned by **Alembic** (`migrations/`), and the SQLAlchemy models under
`src/scrinalia/domains/*/models/` are the single source of truth. `uv run alembic check` must report
no drift; a table that exists only in a migration is a defect.

## Domains and pipeline layers

The system has four domains under `src/scrinalia/domains/`. Three of them are the layers a record
crosses, in order:

- `ingestion` — the scraping queue and the untouched payload (`scraping_queue`, `raw_data`);
- `staging` — the payload parsed into typed, sanitised ISAD(G) columns (`staging_documents`);
- `archive` — the final, enriched description, the catalogues, the AI ledgers and the human review
  (`archive_*`, `domain_*`).

The fourth domain, `identity`, is **not** a layer of that pipeline (ADR 0009). It owns the accounts,
the sessions and the role map — the tables that describe the installation rather than the collection.
The fifth, `diffusion`, is not a layer either: it owns the channels the published set leaves through
and, from #251, the publication scopes over the arrangement (ADR 0023). A record never "passes
through" identity or diffusion.

```text
source site
    │  scrape             │  parse + clean            │  enrich + review
    ▼                     ▼                           ▼
ingestion ──────────▶ staging ──────────────────▶ archive
(scraping_queue,      (staging_documents)         (archive_documents, …)
 raw_data)

identity ── accounts, sessions, roles (not a pipeline layer)
diffusion ── channels and publication (not a pipeline layer)
```

Each layer keys a record on a hash of what it last read, so a re-run knows whether anything moved:
`raw_data.content_hash`, `staging_documents.raw_content_hash` and
`archive_documents.staging_content_hash`. The staging → archive key is the hash of the **parsed**
record, not of the raw payload, so a parser fix reaches the archive even when the origin's bytes did
not change.

## Tables

Every table of `Base.metadata`. To enumerate them from the code:

```bash
uv run python -c "from scrinalia.core.base import Base; import scrinalia.domains.archive.models, scrinalia.domains.diffusion.models, scrinalia.domains.identity.models, scrinalia.domains.ingestion.models, scrinalia.domains.staging.models; print('\n'.join(sorted(Base.metadata.tables)))"
```

### Ingestion — what the origin sent, untouched

| Table | Purpose | Key columns |
| --- | --- | --- |
| `ingestion_origins` | One origin's lifecycle, configuration and agenda: what the operator edits without a deploy. | `code` (primary key), `enabled`, `config` (JSONB: URLs and delay; the `csv` origin has none), `options` (JSONB: the run policy), `cron`, `timezone`, `next_run_at`, `last_enqueued_at`, `last_skipped_at`, `updated_by`, `updated_by_user_id` |
| `scraping_queue` | One row per identifier discovered at the origin, with its extraction state and retry count. | `description_id` (business key, unique), `origin_code`, `scrape_status` (`ScrapeStatus`), `discovered_at`, `last_scraped_at`, `retry_count`, `last_error_message` |
| `raw_data` | The exact payload returned by the adapter, with no typing or cleaning. | `description_id` (unique), `origin_code`, `content_hash`, `raw_title`, `payload` (JSONB), `created_by`, `created_by_user_id` |

`scrape_status` distinguishes a transient failure (`NETWORK_ERROR`, retried) from a permanent one
(`NOT_FOUND`, `FATAL_ERROR`). `raw_data.payload` is the evidence of what the origin actually sent;
nothing downstream reads it directly. `raw_data.created_by` is set by the form-based origins
(`manual`, `csv`): a person typed or uploaded the record, while a scraper has no author — its author
is the origin.

**The origin is provenance, not identity.** `origin_code` is on every layer and on the run ledger,
but `description_id` stays the global business key; an adapter that could collide namespaces its own
ids (`manual-<uuid>`). The origin's **definition** — its adapter and the `SourceSchema` that says
which label fills which staging column — lives next to the adapter in code; the row above is the
lifecycle, and a row whose code left the registry stays readable but cannot run (ADR 0016). The
staging transform resolves the schema **per record**, so one run can read several origins; the
origin is deliberately excluded from `StagingRecord.parsed_content_hash()`, or every row would look
changed once for a column no AI worker writes.

### Staging — the parsed record

| Table | Purpose | Key columns |
| --- | --- | --- |
| `staging_documents` | The sanitised, typed description before any AI touches it: the single source of sanitised truth. | `description_id` (primary key), `origin_code`, `raw_content_hash`, `title`, `document_date`, `date_expression`, `original_url`, `reference_code`, `parent_reference_code`, `hierarchy_path`, `level`, the ISAD(G) text columns, `raw_metadata` (JSONB), `created_at`, `updated_at` |

`parent_reference_code` is optional on purpose: an origin that delivers a child before its parent
leaves the description orphan and *marked* instead of failing the batch. `date_expression` keeps the
date **as the source spelled it** (`Década de 1980`, `1951-1953`) beside the parsed value, because
the parser approximates an expression into a real date and the spelling is the only evidence of that
approximation. `raw_metadata` keeps the keys that did not map to a column.

### Archive — the description and everything around it

#### The description

| Table | Purpose | Key columns |
| --- | --- | --- |
| `archive_documents` | The final cleaned and enriched description, served to users and enriched by the AI workers. | `description_id` (primary key), `origin_code`, `original_title`, `final_title`, `document_date`, `date_expression`, `original_url`, `summary`, `staging_content_hash`, `reference_code`, `level_id`, `typology_id`, `parent_id`, `parent_reference_code`, `path`, the ISAD(G) text columns, `review_status`, `is_anomaly`, `anomaly_reasons`, `execution_log` (JSONB), `embedding` (`vector(384)`), `search_vector` (generated), timestamps |

The **ISAD(G) text columns** are the whole record, not a subset: `dimension_support`,
`producers`, `admin_bio_history`, `admin_archival_history`, `provenance`, `scope_content`,
`appraisal_destruction`, `accruals`, `arrangement`, `access_conditions`, `reproduction_conditions`,
`language_name`, `physical_characteristics`, `finding_aids`, `originals_location`, `copies_location`,
`related_units`, `publication_notes`, `conservation_notes`, `general_notes`, `archivist_notes`,
`rules_conventions` and `description_dates`. The staging transform parsed all of them from the
beginning; the transfer copied a subset until the archive gained the rest, which is why the dossier
can now show and edit the record area by area.

`parent_reference_code` is the parent the origin **declared**, kept even when the link cannot be
resolved yet: the transfer marks the child as pending and the code used to live only inside the
`hierarchy_parent_v1` stamp value. `date_expression` and `original_url` are evidence rather than
editable description: how the source spelled the date, and the page the record was read from.

`language_name` holds the **catalogue's** spelling. The origins do not agree on how to write a
language — the reference collection declared `Português Brasil` in 78 descriptions and
`Português/Brasil` in 22 — so the transfer resolves the declared text against
`domain/language_catalog.py` (accent-, case- and punctuation-insensitive, with the variants declared
as aliases) and writes the canonical name. A language the catalogue does not know is kept exactly as
the source wrote it: the catalogue never replaces a source's word with a guess, and that is what the
dossier's `(fora do catálogo)` marker is for. `staging_documents.language_name` keeps the declared
text, like the level text.

Three properties of this table carry the model:

- `parent_id` is a self-reference with `ON DELETE RESTRICT`. A fund is an archival description like
  any other, so it does not get its own table; and a node with children is not deletable in passing,
  because every descendant's `path` carries its ancestors' ids.
- `path` is the materialised set of ancestor ids (`2368.2732.51931`), maintained by the service and
  never by the AI. It turns "every descendant of X" into one indexed `LIKE 'x.%'`.
- `review_status` (`ArchiveReviewStatus`) is the AI/human lifecycle: `PENDING_AI`, `AI_APPROVED`,
  `NEEDS_REVIEW`, `HUMAN_APPROVED`, `REJECTED`. `HUMAN_APPROVED` blocks AI rewrites.

!!! note "Diffusion is not review"
    Publication is not a column: a record is public because a channel's scope covers it and it is
    `HUMAN_APPROVED` (ADR 0023), and the read is the coverage view. Review is a claim about the
    record; publication is a decision about where it appears. Reusing the status for publication
    would make a typo fix equivalent to publishing, and would lock every published document against
    AI rewriting. Nothing is published by default, so the diffusion surface is born empty.

#### Subjects, categories and entities

| Table | Purpose | Key columns |
| --- | --- | --- |
| `archive_tags` | A subject term of the collection. | `tag_id`, `name` (unique), `macro_category_id`, `ai_confidence_score`, `execution_log` (JSONB) |
| `archive_macro_categories` | The subject category (the "about" axis). | `category_id`, `name` (unique), `description`, `classifier_label`, `is_active` |
| `archive_entities` | A named entity (person, organisation, place) found by NER or inserted by hand. | `entity_id`, `name` (unique), `entity_type` |
| `archive_entity_merge_log` | One row per absorbed entity (a **merge**) or per renamed name (a **rename**), snapshotted before anything changes. | `kind` (`MERGE`/`RENAME`, checked), `canonical_renamed_from`, `renamed_from_synonym_created`, `undone_at`; `undo_entity_merge` restores the row, its links, its spellings and the name the canonical lost. |
| `archive_document_tags` | Which tags a description carries. | `(description_id, tag_id)` composite key |
| `archive_document_entities` | Which entities a description carries, and who wrote each link. | `(description_id, entity_id)` composite key, `origin` (`ArchiveEntityOrigin`: `AI`, `HUMAN` or `UNKNOWN`), `created_at` (null when the link predates the column) |
| `archive_ai_review_queue` | The AI auditing queue; the decision side of a tag × entity collision. | `anomaly_type` (`AnomalyType`), `status` (`ArchiveReviewStatus`), `context_payload` (JSONB), `llm_decision`, `llm_confidence`, `llm_reason` |

`archive_tags.macro_category_id` holds at most one subject category, and that is the whole subject
axis: a tag is in a **drawer**, declared **not a subject**, or undecided (ADR 0013). What a name *is*
when it is not an aboutness — a place, a producer, a person — is carried by the **entity axis**, where
it has an `entity_type` that search and the public projection read; a spelling that is both a tag and
an entity is settled by the tag × entity conflict resolution, which bans the losing spelling and keeps
a ledger. `archive_tag_facets` used to hold that distinction as a second state of the tag; its only
reader was the state chip it fed, and it was dropped.

The identity of a tag and of an entity is the normalized spelling: `lower(btrim(name))` is unique on
both tables, next to the unique `name` itself. Without that rule a row stored in Title Case and the
lowercase row for the same name are two rows, and the insert path — which normalizes the spelling and
looks the existing ids up with it — can never see the first.

#### The arrangement

| Table | Purpose | Key columns |
| --- | --- | --- |
| `archive_description_levels` | The description-level ladder (the NOBRADE/ISAD(G) rungs), owned by the archivist. | `level_id`, `ordinal` (unique), `code` (unique), `name` (unique), `description`, `aliases`, `requires_parent`, `allows_children`, `is_active` |
| `archive_hierarchy_node_plans` | One rung the reference codes imply, and the archivist's decision about it: a proposal, not a write. | `plan_id`, `code` (unique fingerprint), `depth`, `parent_code`, `document_count`, `declared_levels`, `flags`, `existing_description_id`, `level_id`, `title`, `reference_code`, `status`, `collapse_into_code`, `materialised_description_id`, `decided_by`, `decided_at` |
| `archive_hierarchy_materialisation_log` | The ledger of one materialisation run, with enough detail to reverse it. | `materialisation_id`, `created_nodes` (JSONB), `rung_map` (JSONB), `previous_state` (JSONB), `changed_by`, `changed_by_user_id`, `undone_at`, `undone_by`, `undone_by_user_id` |

`requires_parent` means "a node at this level may not be a root"; `allows_children` means "a node at
this level is a leaf". The staging load records an unknown level as unclassified and carries on; a
typology chosen by a person is a claim the catalogue must answer.

#### The curation trail of the description

| Table | Purpose | Key columns |
| --- | --- | --- |
| `archive_document_revisions` | Every human edit of a description, before and after. | `revision_id`, `description_id`, `changed_by`, `changed_by_user_id`, `changes` (JSONB), `note`, `created_at` |
| `archive_document_deletions` | The ledger of the one destructive write over the collection. | `deletion_id`, `description_id`, `reference_code`, `title`, `level_name`, `snapshot` (JSONB), `children_count`, `deleted_by`, `deleted_by_user_id`, `note`, `deleted_at` |

`description_id` in `archive_document_revisions` is `ON DELETE CASCADE`, so a revision written for a
deleted document dies with it. `archive_document_deletions` therefore carries **no foreign key** to
`archive_documents`: the row it names is gone by design, and this ledger is what outlives it. It is
not a restore path — there is no code that writes the snapshot back.

#### Governance tables

These tables are named `domain_*` although they live under `domains/archive/`: they are statements
about the domain of the archive, not about the installation.

| Table | Purpose | Key columns |
| --- | --- | --- |
| `domain_stopwords` | Terms the curation banned, with the axis they leave, who planted the ban and how the ban matches a name. | `id`, `word` (unique), `word_scope` (`StopwordsScope`: `TAG`, `ENTITY`, `ALL`), `source` (`HUMAN`/`CONFLICT`/`EXCLUSION`, checked), `match_mode` (`StopwordMatch`: `TOKEN`/`EXACT`, checked; only the `ENTITY`/`ALL` axes read it) |
| `domain_ner_exclusions` | Terms the curation decided belong to the TAG axis, not to named entities; matched by the **exact spelling**, never by a token. | `id`, `term` (unique), `reason`, `source` (`JUDGE`/`HUMAN`), `tag_id` |
| `domain_subject_exclusions` | Terms the curation decided are not a subject at all, with whether this row planted the `TAG`-scoped ban. | `id`, `term` (unique), `reason`, `source` (`HUMAN`/`RULE`), `ban_created` |
| `domain_synonyms` | Spellings mapped to a canonical tag or entity. | `id`, `synonym_name`, `category` (`TAG`/`ORG`/`LOC`/`PER`), `canonical_tag_id`, `canonical_entity_id` |
| `domain_text_templates` | Repeated excerpts the curation keeps out of the AI text. | `template_id`, `text`, `fingerprint` (unique), `variants`, `action`, `replacement`, `scope`, `status`, `occurrence_count`, `sample_document_ids` |
| `archive_cleaning_rules` | Regex rules an archivist registered. | `rule_id`, `rule_name`, `rule_kind` (`REWRITE`/`VALIDATE`/`LLM_CHECK`), `target_column`, `regex_pattern`, `replacement_string`, `anomaly_reason`, `engine_name`, `preset`, `is_active` |

`domain_synonyms` has an exclusive-arc check: a `TAG` row points at a tag and not at an entity, and
the other categories point at an entity and not at a tag. Canonicalising a spelling deletes the old
row, which is why the taxonomy search reads this table too.

`domain_text_templates.scope` (`EMBEDDING`, `NER`, `TITLE`) says which consumer stops reading an
excerpt. The split exists because measurement showed one excerpt can help one consumer and hurt
another: removing a title prefix from the *embedded* text hurt the ranking while being exactly what
the title suggestion needs.

`archive_cleaning_rules.rule_kind` separates `REWRITE` (the cleaning worker replaces the match) from
`VALIDATE`/`LLM_CHECK` (the quality validator only flags). The cleaning worker filters `REWRITE`
explicitly; without it a validation rule would rewrite the text.

#### The collection vocabulary (data, not code)

| Table | Purpose | Key columns |
| --- | --- | --- |
| `archive_arrangement_vocabulary` | One arrangement token and the name the hierarchy proposal suggests for its rung. | `term_id`, `token` (unique, normalised), `display_name`, `is_active` |
| `archive_collection_terms` | A term the collection carries that is not a subject, with the axis it goes to instead. | `term_id`, `(term, kind)` unique, `kind` (`CollectionTermKind`), `is_active` |

`token` is either a single code token (`ED`, `ALFA`) or a whole code (`ACERVO RAIZ`). The proposal
reads the whole code first and falls back to its last token, so a full-code row wins over a
last-token row. `CollectionTermKind` is `DISTRICT`, `MUNICIPALITY`, `STATE`, `REGION`, `COUNTRY` or
`PERSON`; a place kind and `PERSON` mark the terms the **entity axis** carries (`LOC`, `PER`), which
is what the subject axis stops guessing at — they are not a state of the tag.

#### Operations

| Table | Purpose | Key columns |
| --- | --- | --- |
| `archive_worker_settings` | The persisted default configuration of one worker. | `worker_name` (primary key), `engine_name`, `preset`, `db_batch_size`, `options` (JSONB), `updated_by`, `updated_at` |
| `archive_worker_settings_revisions` | Audit trail of configuration writes, one row per write. | `id`, `worker_name`, `before` (JSONB), `after` (JSONB), `changed_by`, `changed_by_user_id`, `changed_at` |
| `archive_worker_runs` | One row per worker execution, from the CLI and from the panel alike; since ADR 0014 a `QUEUED` row is also the queue item a runner claims. An ingestion run names the origin it processed in `origin_code` and a diffusion run names the channel it wrote in `channel_code`; an archive worker's run leaves both null. A **trial** (`trial = true`, ADR 0018) is a comparison of configurations that writes no archival content and carries its measurements in `trial_result`; it holds the worker's slot like any run, but the panel's "last run" ignores it. | `id`, `worker_name`, `origin_code`, `channel_code`, `status` (`WorkerRunStatus`), `trigger` (`WorkerRunTrigger`), `trial`, `requested_by`, `requested_by_user_id`, `engine_name`, `preset`, `request` (JSONB, the validated request), `config` (JSONB), `options` (JSONB), `trial_result` (JSONB), `attempt`, `retry_of`, `not_before`, `queued_at`, `runner_id`, `started_at`, `heartbeat_at`, `lease_expires_at`, `cancel_requested_at`, `cancel_requested_by`, `cancel_requested_by_user_id`, `finished_at`, `duration_ms`, `error`, `error_fingerprint` (generated) |
| `archive_worker_schedules` | The agenda of one worker: a five-field cron in an explicit zone, the pinned request it runs and the next run. | `worker_name` (primary key), `enabled`, `cron`, `timezone`, `request` (JSONB, the validated request), `next_run_at`, `last_enqueued_at`, `last_skipped_at`, `updated_by`, `updated_by_user_id`, `created_at`, `updated_at` |
| `archive_worker_runners` | The live runner registry: who is connected, which workers it accepts, and when it last signalled. | `runner_id` (primary key), `name`, `hostname`, `version`, `capabilities` (text array), `concurrency`, `heartbeat_seconds`, `started_at`, `last_heartbeat_at`, `stopped_at` |
| `archive_api_errors` | The API's own unexpected HTTP failures. | `id`, `occurred_at`, `request_id`, `method`, `path`, `status_code`, `message`, `error_fingerprint` (generated) |

`archive_worker_settings` is a **partial** row on purpose: a field left `NULL` keeps following the
code, so the precedence is `explicit argument > this row > the signature default`. `archive_worker_runs`
carries the **resolved** configuration — `config` for the engine, `options` for the worker's own
options, resolved when the run starts — so the row keeps its meaning when a preset or a code default
changes in code. Since ADR 0014 the run ledger is also the queue: a `QUEUED` row carries the validated
`request`, so a runner reproduces the execution without the process that accepted it, and the claim
writes `runner_id`, `started_at`, `heartbeat_at` and `lease_expires_at` with PostgreSQL's clock. The
runner renews the lease; a claim whose lease expires is marked `INTERRUPTED` by the next runner, never
by the API's boot. `archive_worker_runners` is the registry the panel reads to answer whether a runner
is alive and whether it can run a given worker.

`archive_worker_schedules` is one row per worker because the queue is one slot per worker: two
agendas for the same worker would only collide. `next_run_at` is what the scheduler's tick reads;
`last_enqueued_at`/`last_skipped_at` are the facts the panel shows. The retry's columns are the three
the ledger needs to explain a second attempt: `attempt` (1 for a run asked once), `retry_of` (the
failed row) and `not_before` (when the claim may take it). A retry is a new row created after the
previous one is terminal, so the partial unique index is never violated (ADR 0015).
There is deliberately no foreign key from either table to a worker table: workers are code, not rows.
`archive_api_errors` records only *unexpected* failures — a 404, a 409 and a 422 are answers the API
owes a client, and recording them buries the real defects.

### Diffusion — where the published set leaves

| Table | Purpose | Key columns |
| --- | --- | --- |
| `diffusion_channels` | One channel's lifecycle, configuration and agenda: what the operator adds and configures without a deploy. A `LIVE` channel is read on every request; an `EXPORT` channel has an agenda and a run. | `code` (primary key), `enabled`, `config` (JSONB: the channel's presentation identity; never a secret), `options` (JSONB: the run policy), `cron`, `timezone`, `next_run_at`, `last_enqueued_at`, `last_skipped_at`, `updated_by`, `updated_by_user_id` |
| `diffusion_channel_scopes` | The positive scope: "this branch or record goes to this channel". Its approved descendants are covered on read from the materialised `path`, so a child approved later enters without a second decision. Revoking writes `revoked_at`; the row is never deleted, because it records that the decision was taken. | `scope_id` (primary key), `channel_code` (FK → `diffusion_channels`, `RESTRICT`), `node_id` (FK → `archive_documents`, `CASCADE`), `include_descendants`, `note`, `created_by`, `created_by_user_id`, `created_at`, `revoked_at`, `revoked_by`, `revoked_by_user_id` |
| `diffusion_channel_exclusions` | The negative scope: "this branch or record stays out of this channel", with the curator's reason. It overrides any positive scope that covers the same record. | the positive scope's shape plus `reason` |
| `diffusion_publication_batches` | One publication gesture — publish a ramo, publish a selection, keep a record private, revoke a ramo — with the resolved selection, the counts and the author. It is the reversible unit of principle VI. | `batch_id`, `action` (`PUBLISH`/`EXCLUDE`/`REVOKE`/`UNEXCLUDE`), `selection` (JSONB), `applied_count`, `skipped_count`, `note`, `requested_by`, `requested_by_user_id`, `created_at`, `undone_at`, `undone_by`, `undone_by_user_id` |
| `diffusion_publication_entries` | Each scope row a batch created or revoked, with the state before and after and a snapshot of the node. The undo reads it and skips what changed since; the node is a snapshot and not a foreign key, so a deleted or moved branch still has an explanation. | `entry_id`, `batch_id` (FK, `CASCADE`), `channel_code`, `kind` (`INCLUSION`/`EXCLUSION`), `scope_id`, `node_id`, `node_path`, `node_title`, `include_descendants`, `was_active`, `is_active`, `created_at` |

A diffusion channel is a definition in code plus this lifecycle row (#211, ADR 0023). The registry only
ships channels that work: `public_site` is `LIVE` and has no run, while the dataset and AtoM are
`EXPORT` channels with their own adapters. `enabled=false` is a pause, not an absence; a missing row
is "never added", which is what the `configured` flag on the DTO distinguishes. `config` never holds a
secret — a token is named by an environment variable, not stored here.

The records a channel exposes are a **read**, not a table. Two views, one concept each:
`archive_document_channel_exclusions` is the negative set — which exclusion covers a record on which
channel — and `archive_document_channels` composes it with the approval and the positive scopes. The
coverage view returns one row per (description, channel) when the record is `HUMAN_APPROVED`, a
positive scope covers it and no negative scope does, and it names the scope that is the origin of the
coverage (`scope_id`), so a screen can say "pelo ramo do Fundo A" without re-implementing the
predicate. The split is what lets the curator's preview say *why* a record is skipped — "excluded"
rather than "not covered" — without a second copy of the exclusion rule. The view reads the materialised `path` and the
node's current position, so moving a branch moves what it covers; it does **not** read `enabled`,
because pausing a channel is the operator's decision and the curator's "Publicadas" must keep saying
what was published. `DocumentSummary.channels` is the list the dossier and the collection show, and
`is_published` is derived from it: covered by at least one channel. There is no stored boolean — the
`archive_documents.is_published` column was dropped, and the migration refuses to drop it while a
row still carries a true.

### Identity — the installation, not the collection

| Table | Purpose | Key columns |
| --- | --- | --- |
| `auth_users` | One person who can sign in. | `user_id`, `email` (normalised, unique), `name`, `password_hash` (argon2id), `role` (`Role`), `is_active`, `must_change_password`, `failed_attempts`, `locked_until`, `last_login_at` |
| `auth_sessions` | One live sign-in, revocable. | `session_id`, `user_id`, `token_hash` (SHA-256, unique), `created_at`, `last_seen_at`, `expires_at`, `revoked_at`, `user_agent`, `ip_address` |

An account is deactivated (`is_active`), never deleted: every ledger in the archive stores who
decided what, and the `*_user_id` columns are `ON DELETE SET NULL`, so deleting the account would
erase the *who* of decisions that still stand. `auth_sessions` stores only the SHA-256 of the token,
never the token, so a database dump cannot be replayed as a cookie. `ON DELETE CASCADE` from
`auth_sessions` to `auth_users` is right here and nowhere else in this domain: a session has no
meaning without its account.

## Idempotency: `execution_log` and versioned stamps

Every AI worker is re-runnable. Instead of leaving a business column nullable and hoping, each worker
writes a **versioned key** into a JSONB `execution_log`, and its pending query filters on the
*absence* (or difference) of that key:

- document workers stamp `archive_documents.execution_log`;
- `worker_macro_category` stamps `archive_tags.execution_log`, because its unit of work is the tag.

The canonical keys, defined once in `worker_stamp.py`:

| Stamp key | Written on | Meaning |
| --- | --- | --- |
| `worker_ner_v2` | `archive_documents` | Value is the identity of the extractor that ran |
| `worker_typology_classifier_v2` | `archive_documents` | Value is the identity of the classifier that ran |
| `cleaning_rule_{id}` | `archive_documents` | The dynamic cleaning rule with that id has run |
| `worker_macro_category_v1` | `archive_tags` | Value is the label set composed with the identity of the classifier |
| `worker_quality_validator_v1` | `archive_documents` | Value is the identity of the active `LLM_CHECK` rule, or of "no model" |
| `worker_embedding_v1` | `archive_documents` | Value is the MD5 of the embedded text followed by `:` and the identity of the model |
| `thumbnail` | `archive_documents` | Miniature in the object storage; the queue is led by `storage_thumbnail_uri`, so this key is declared but not written |
| `thumbnail_failed` | `archive_documents` | The miniature download failed; the value is `ERROR`; a plain run skips it, `force` retries it |
| `hierarchy_parent_v1` | `archive_documents` | Value is `PENDING:<code>` while the declared parent is missing and `DONE:<description_id>` once linked |
| `curated_macro_category` | `archive_tags` | Value is who, when and the destination of a curator's subject decision |

The polling queries are served by GIN indexes on the JSONB column: `ix_archive_exec_log` on
`archive_documents` and `ix_archive_tags_exec_log` on `archive_tags`. A worker mutates the dict and
must call `flag_modified` so SQLAlchemy notices the in-place change; skipping it is how a stamp is
written in memory and never in the database.

Most stamps hold a status (`DONE`, `ERROR`). The five that key a queue on **what produced the answer**
are a different type (`WorkerStamp` against `IdentityStamp`), and the type is what enforces the
difference: an identity slot accepts only a value its own `fingerprint_pattern` matches, so a status
raises `ValueError` instead of being written, and a failure goes through `mark_failed`. That value is
the *producer identity* — a fingerprint of the engine, the preset, the resolved engine configuration,
the installed versions of the libraries of that axis and the declared behavioural options
(`producer_fingerprint` in `worker_stamp.py`). A unit stamped by another producer is pending again by
itself:

- `worker_ner_v2`, `worker_typology_classifier_v2` and `worker_quality_validator_v1` store that
  identity — the last one taken from the engine of the active `LLM_CHECK` rule, or from "no model" —
  so another engine, preset, threshold, column set or dependency version re-queues the units. `force`
  is the way back from a reason a hash cannot see (an edited rule, a curated exclusion, a prompt).
- `worker_embedding_v1` composes it with the **MD5 of the embedded text**, computed by PostgreSQL
  (`func.md5(...)` over the effective text) in the same expression that builds the text
  (`embedding_stamp_sql`), so a text change — including a human edit — and a model or dependency bump
  each put the document back in the queue by itself.
- `worker_macro_category_v1` composes it with the hash of the label set the tag was classified
  against, so rewriting a curator's label re-queues the tag.
- `hierarchy_parent_v1` stores `"PENDING:<code>"` while the child waits for the parent its origin
  declared and `"DONE:<description_id>"` once the link exists, so the retry remembers which parent was
  missing.
- `curated_macro_category` stores who, when and the destination of a curator's subject decision — free
  text, not a status, so a tag a person filed reads as curated rather than as one the machine got right.

The five identity slots were rewritten once by
`a7c1e5b9d3f2_make_the_legacy_identity_stamps_read_as_unknown.py`: every `"DONE"` in one of them —
the current key or a retired one (`worker_ner_v1`, `worker_typology_classifier_v1`) — became
`PRODUCER_UNKNOWN`, a name that reads as what it is and is deliberately not a fingerprint, so
`identity_stamp_conditions` still calls those units pending. The migration invents no producer and
touches no missing key: the 3,100-odd documents with no NER slot keep having none, because what is
true about them is that nothing recorded a run. It also leaves the embedding's rows alone: those
carry the bare MD5 of the text they embedded, from before the identity was composed into the value,
and the text hash is a fact while `PRODUCER_UNKNOWN` would replace it with a false one. The panel
reads it as "no producer" by the slot's own pattern.

!!! note "One documented exception"
    `worker_embedding` deliberately does not use `ai_writable_documents()`. The embedding is a
    derived index of the text rather than archival content, so a `HUMAN_APPROVED` document whose text
    changed must be re-embedded or semantic search would serve a stale vector. It writes only the
    `embedding` column and its own stamp, and `REJECTED` documents are skipped.

## Bidirectional governance

A tag × entity collision has two possible verdicts, and the two directions are stored in **different
tables on purpose**.

| Verdict | Where the decision is stored | What it means |
| --- | --- | --- |
| In favour of the **entity** | `domain_stopwords` (tag-scoped) | The tag name is noise on the subject axis and is dropped from it |
| In favour of the **tag** | `domain_ner_exclusions` | The term is a legitimate subject; a NER extraction of it is a false positive |

`domain_stopwords.word` is **unique**, so a term lives on exactly one axis. Re-banning a term on the
blocked-spellings screen *moves* it (`save_stopwords` is an upsert on `word`) rather than leaving the screen
showing an axis the archivist just changed away from. `word_scope` is `TAG`, `ENTITY` or `ALL`, and
`source` (`HUMAN`, `CONFLICT` or `EXCLUSION`) says who planted the ban — the origin the purge preview
reads to tell a term banned with the archive in mind from one typed by hand.

The two writes of one ban are not the same write. `save_stopwords` **moves** the scope, because that is
the archivist changing their mind on the screen; `TagRepository.ensure_tag_ban` — what the *Não é
assunto* screen and the conflict resolution use — **never narrows**: an `ENTITY` veto becomes `ALL`,
and an existing `TAG`/`ALL` is left alone. Writing `TAG` over an `ENTITY` veto would silently stop the
NER from extracting a name the archivist had deliberately kept, which is why the coupling uses the
second write.

`TagRepository.get_stopwords_with_source()` reads **only** `TAG`/`ALL` scope. An `ENTITY`-scoped veto
is a ban on NER extraction, not a statement about the subject axis; reading it there once made the
curation purge delete tags the curator had deliberately kept. That is the reason the two directions
cannot be collapsed into one table or one scope.

`domain_ner_exclusions` is a *decision*, not noise: it carries `reason`, `source` (`JUDGE` for the
LLM conflict judge, `HUMAN` for a curator) and the `tag_id` that justifies it. The `tag_id` is
`ON DELETE SET NULL`, so deleting the tag does not silently re-open the false positive this row
exists to prevent. The row itself **deletes nothing**: the entities already extracted from the
spelling are removed by the NER purge, a separate act with its own preview and its own ledger
(`archive_ner_purge_log`).

`domain_subject_exclusions` is the same shape for the other axis: a term the curation decided is not a
subject at all. The deterministic guard covers what has a recognisable form (a bare year, a
placeholder, a street, a measure); the semantic half (`pessoas`, `vista aérea`) is a decision, and it
lives here with `source` (`HUMAN` or `RULE`). Confirming also **bans the spelling** at `TAG` scope, so
the next ingestion does not recreate the tag; the ban deletes nothing, and `ban_created` records
whether *this* row planted it, which is what makes the undo exact. The write refuses a term whose tag
already sits in a drawer — that drawer is a human verdict about the tag, and a statement about a term
must not un-file it. An excluded term is still a tag of the collection, reachable by search until the
purge — a separate act — removes it.

## Ledgers, one by one

A ledger is a table whose job is to make a write explainable or reversible. They are not
interchangeable, and only some of them have an undo.

| Ledger | What it records | Its undo |
| --- | --- | --- |
| `archive_taxonomy_merge_log` | One row **per absorbed tag**, snapshotted before anything changes. | `undo_merge` restores the row, its links, its classification and the spelling state. |
| `archive_entity_merge_log` | One row **per absorbed entity** (a **merge**) or **per renamed name** (a **rename**), snapshotted before anything changes. | `undo_entity_merge` restores the row, its links, its spellings and the name the canonical lost; a **rename** row only puts the name back. |
| `archive_stopword_purge_log` | One row **per tag the stopword purge deleted**, snapshotted before the delete: the row, the documents that carried it and the spellings that pointed at it. | `undo_stopword_purge` restores the row, its links and its spellings; the ban stays, so the next purge lists the tag again. |
| `archive_ner_purge_log` | One row **per entity the NER purge deleted**, snapshotted before the delete: the entity, the documents that carried it, the spellings that pointed at it and the `excluded_term` that justified it. | `DELETE /entities/ner-exclusions/purge-log/{id}` restores the entity, its links and its spellings; the veto stays, so the next purge lists the entity again. |
| `archive_hierarchy_materialisation_log` | One row per materialisation run: the nodes it created and the previous parent/path of every row it changed. | The undo restores `previous_state` and then removes `created_nodes`. |
| `archive_conflict_resolution_log` | One row per tag × entity resolution: the loser's snapshot, the transferred links, the spellings that pointed at the loser and the ban it planted. | `DELETE /conflicts/resolutions/{id}`. |
| `archive_document_deletions` | One row per deleted description, with the whole ISAD(G) snapshot. | **No undo.** The snapshot is evidence; nothing writes it back. |
| `archive_worker_runs` | One row per worker execution, CLI and panel alike. | **No undo** — it is an execution history, not a change to the collection. |
| `archive_api_errors` | One row per unexpected HTTP failure. | **No undo** — an error ledger is a trace. |

Two details make the reversible ledgers exact rather than approximate. `created_link_ids` records the
links the operation *created*; both merges and the conflict resolution link with
`ON CONFLICT DO NOTHING`, so an undo that deleted every link would remove links that existed before
it. `ban_created` plays the same role for the two writes that plant a ban — the conflict resolution and
the subject exclusion: the undo must remove the ban only when this row is the one that planted it, or
reversing one decision would lift a ban an earlier one made. The subject exclusion adds a second guard
— the ban's `source` must still name it (`EXCLUSION`), so a spelling a person re-banned on the
blocked-spellings screen keeps its ban — while the conflict resolution's undo guards on `ban_created` alone.
For a merge, `synonym_created` and `synonym_previous_tag_id` (tag) / `synonym_previous_entity_id`
(entity) capture the spelling state before the merge, and `repointed_synonym_names` records the
spellings that pointed at the absorbed row and were moved to the canonical. `undone_at` keeps the undo
single-shot and keeps the trail readable afterwards: the row is never deleted.

`archive_ai_review_queue` is the companion of `archive_conflict_resolution_log`, not a ledger of
writes: it keeps the *decision* (the judge's verdict or the human's), while the resolution log keeps
the *write*. It also carries `AnomalyType.SUBJECT_LOW_CONFIDENCE` for tags the subject classifier
could not place, and `AnomalyType.TYPOLOGY_LOW_CONFIDENCE` for descriptions it refused to classify —
that row is where the **score the run saw** is kept, because `typology_id` stays NULL both when the
classifier declined and when no run reached the description (issue #110).

`archive_worker_settings_revisions` is a revision ledger in the same spirit: the decision and the
write are different facts, and every configuration change leaves a `before`/`after` row.

## Generated columns: one definition, in the database

Two columns are computed by PostgreSQL and never written by application code.

| Column | Table(s) | Definition |
| --- | --- | --- |
| `search_vector` | `archive_documents` | `setweight(to_tsvector(<dictionary>, public.immutable_unaccent(title columns)), 'A')` concatenated with the body at weight `'B'` |
| `error_fingerprint` | `archive_worker_runs` (over `error`), `archive_api_errors` (over `message`) | `public.archive_error_fingerprint(<column>)` |

`search_vector` is what lexical search runs against, with the GIN index
`ix_archive_documents_search_vector`. The dictionary comes from the language profile
(`get_language().fts_dictionary`), and `immutable_unaccent` makes it accent-insensitive, so `gaucho`
finds `Gaúcho`. Because the column is **stored**, changing `ACERVO_LANGUAGE` is a migration that
rebuilds it, not a reboot — and `alembic check` reports exactly that drift instead of letting the
model and the stored expression disagree in silence.

`archive_error_fingerprint(text)` is `IMMUTABLE` and reduces an error message to its root cause: the
first line, lowercased, with uuids, hashes, numbers and paths replaced by placeholders. It is created
by the migration `fe7fcab37207` and **mirrored in `testing/conftest.py`**, because the test schema is
built by `Base.metadata.create_all` and the function has to exist before `create_all` emits the
generated column that calls it — exactly like `immutable_unaccent`. The `public.` prefix is part of
the expression because that is how PostgreSQL reflects it back.

The reason both are generated and not application writes is that a generated column backfills the
existing rows with the very expression the new rows get. There is exactly one definition, it cannot
drift from the code that writes the message, and the error text is written with its exception class
(`KeyError: 'nome'`) precisely so the fingerprint can tell two failures apart.

## Proposals that outlive what they name

| Table | Purpose | Key columns |
| --- | --- | --- |
| `archive_tag_merge_proposals` | A cluster of tags the routine proposes to unify, and the human decision about it. | `proposal_id`, `fingerprint` (unique), `canonical_id`, `canonical_name`, `members` (JSONB), `reason`, `review_flags`, `total_documents`, `status`, `decided_by`, `decided_by_user_id`, `decided_at`, `decision_note` |
| `archive_hierarchy_node_plans` | One rung the reference codes imply, and the archivist's decision about it. | see "The arrangement" above |

A proposal is **evidence plus a decision, never a write**. The status ladder is
`SUGGESTED → APPROVED/REJECTED → APPLIED`: a human verdict is a durable intent that the suggestion
run never overwrites (`fingerprint` makes the suggestion idempotent), and applying the cluster writes
`APPLIED` in the same savepoint that absorbs the tags. `decided_by`/`decided_at` keep the *verdict*;
the merge ledger keeps the *when*.

`canonical_id` and `members` are **snapshots without a foreign key**, deliberately: applying the
proposal deletes those tags, and the proposal has to survive as the record of what was decided. The
cluster is identified by its spellings, not by its ids. Because the members can die, the read
computes `members_alive`, `canonical_alive` and `applicable` (canonical alive **and** more than one
member alive) in one query per page; `applicable` is the single definition of "there is still work".

## Catalogues retire, they do not delete

The three catalogues the archivist extends without a deploy are `archive_description_levels` (the
level ladder), `archive_macro_categories` (the subject categories) and `archive_typologies` (the
documental typologies — the *diplomatic form*: ata, ofício, planta). The collection vocabulary adds
`archive_arrangement_vocabulary` and `archive_collection_terms`. All of them are tables instead of
enums so a name can change without a release.

None of them deletes. The foreign keys are `SET NULL` (`archive_documents.level_id`,
`archive_documents.typology_id`, `archive_tags.macro_category_id`), so removing a row would
unclassify every description pointing at it while erasing the record that it ever existed. A row
retires with `is_active=false` — `archive_tags` is the exception: a tag has no such column and leaves
through the merge and stopword-purge ledgers — and that is also the only lever that reaches the
classifier: retiring a typology removes it from the candidate labels without touching a single
classified description, so the catalogue screen keeps showing the weight of the retired ones.

Two rules hold the typology catalogue: `get_active_typologies()` projects **only**
`(typology_id, name)` and filters `is_active` — the bare name is the label, because appending
`context_description` makes the model lose the entailment as the label grows — and an archivist
choosing a typology is making a claim the catalogue has to answer, so an unknown id is refused with
422 rather than stored as `NULL`.

The language is **code**, not data: `core/language/` holds one frozen profile per language
(stopwords, date grammar, street and placeholder patterns, plural rules, the FTS dictionary, the spaCy
model) and `ACERVO_LANGUAGE` selects it. The collection vocabulary is a row precisely because another
institution's collection carries other names. See ADR 0008.

## The public surface: an exact partition

The diffusion surface reuses `DocumentService` and differs only in projection. The internal read view
is `DocumentSummary`; the public one is `PublicDocumentSummary`, built **field by field** and never
with `model_validate` on the internal DTO — validating it would make every field the internal view
gains automatically public.

Two frozensets in `api/schemas/public.py` make the default private:

- `NOT_PUBLIC_FIELDS` — fields of `DocumentSummary` that are deliberately not published. It contains
  `review_status`, `is_anomaly`, `anomaly_reasons`, `archivist_notes`, `provenance`,
  `suggested_final_title`, `rank`, `path`, `parent_id`, `level_id`, `typology_id`, `is_published`, `channels`,
  `admin_bio_history`, `admin_archival_history` and `access_conditions`.
- `NOT_PUBLIC_FACETS` — currently just `anomaly_reason`.

Together with the published fields and facets they must remain an **exact partition** of the internal
read: every field is either published or listed, and none is both. A test fails when a new field or
facet is left unclassified, so the default for whatever the internal view gains next is private.

Two more rules complete the surface. `published_only` is set **server-side** and is not a client
parameter, so no query string can ask for an unpublished record. An unpublished id answers **404, not
403**: a distinct status would confirm that the description exists. And `published_only` is a filter
that is never excluded from facet counting — no facet may lift the diffusion gate.

## The revision trail of human curation

`archive_document_revisions` is where a person's edits become evidence. `PATCH /api/v1/documents/{id}`
writes one row holding the before/after of every field that actually changed, in `changes` (JSONB),
and sets the document to `HUMAN_APPROVED`. Linking and unlinking tags and entities writes the same
kind of row, storing the whole list of names on each side rather than a diff of ids; a repeated call
that changes nothing writes no revision.

Authorship is **two columns, never one**:

| Column | What it holds | On account deletion |
| --- | --- | --- |
| `changed_by` | The name the history prints — a snapshot of who they were. | Kept; renaming somebody does not rewrite what they decided. |
| `changed_by_user_id` | The account behind the name, as a foreign key. | `SET NULL`; the decision survives with its author's name. |

The same pair appears wherever a person decides something: `archive_document_deletions` (`deleted_by`
/ `deleted_by_user_id`), `archive_taxonomy_merge_log` (`changed_by`, `undone_by`),
`archive_stopword_purge_log` (`changed_by`, `undone_by`), `archive_ner_purge_log` (`changed_by`,
`undone_by`), `archive_entity_merge_log` (`changed_by`, `undone_by`),
`archive_conflict_resolution_log` (`decided_by`, `undone_by`), `archive_hierarchy_node_plans` and
`archive_tag_merge_proposals` (`decided_by`), `archive_cleaning_rules` and
`domain_text_templates` (`created_by`), `archive_hierarchy_materialisation_log` (`changed_by`),
`archive_worker_runs` (`requested_by`) and `archive_worker_settings_revisions` (`changed_by`). The
author is written by `author_columns`/`assign_author` from the session, never taken from the request.
