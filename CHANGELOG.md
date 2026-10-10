# Changelog

All notable changes to this project are documented here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`1.0.0` was the first release; the newest one is at the top. Entries describe **behaviour**, not
commits — the history is the detail.

## [1.1.0] - 2026-10-10

### Added

- **First-run setup, without an open door** (ADR 0011): `GET /api/v1/setup/status` and
  `POST /api/v1/setup/admin` create the first `ADMIN` once, in a single transaction under
  `LOCK TABLE auth_users IN EXCLUSIVE MODE`, and answer 409 for ever after. The SPA draws the setup
  form while the installation has no account, accepting only a positive `needs_setup`, so an error
  can never open the form that creates an administrator. The password is the one the person chose,
  the role is not a request field, and the account does not carry `must_change_password`.
- **Password recovery has a front door**: the sign-in screen says what the path is — ask an
  administrator, who resets it on *Configurações › Usuários*; the reset ends every session of the
  account and lifts a lockout; and the host's `identity` CLI is the last resort when no administrator
  can get in. The accounts screen resets a password from the account's own row and warns, before the
  click, that resetting your own account signs you out.
- **The worker settings are a screen of their own** (`/configuracoes/workers`, issue #53): the
  persisted override of each worker, its revision history and the engine/preset choice, behind
  `GET /api/v1/system/workers/settings`. `/sistema/workers` keeps the machine — the queues, the
  pending and failed counters, and *Rodar agora* — and shows the effective configuration **read
  only**. The precedence is unchanged: explicit argument > persisted row > signature default.
- **`/configuracoes` is a card landing** (issue #22): the screens nobody opens in the middle of
  cataloguing — the arrangement plan, the catalogues, the worker surfaces, the run ledger, the
  diagnostics and the accounts — are cards on three tabs, and the menu goes from 23 entries to 16.
  `lib/settings.ts` is the single definition the page and the menu entry both read.
- **A generated contract that declares the system**: `info.title` is `Scrinalia API` and
  `info.version` is the installed distribution's version, instead of the framework default
  (`Litestar API`, `1.0.0`) that no version bump moved. A gate
  (`testing/unit/api/test_openapi_metadata.py`) fails when the contract, the distribution and
  `pyproject.toml` disagree.
- **The curator's visual identity**: the palette and the logomark in the rail, the header rule and
  the plates before a session, and the installation's version alone at the foot of every page —
  including the three screens that come before a session.
- **The shell is one window tall**: only the content column scrolls, the header is sticky, the menu
  folds into one open section plus the one you are standing in, and it collapses to an icon rail.
- **A constitutional `AGENTS.md`**: eight general principles with the rationale and the incident that
  produced each, and the topic-specific rules in fourteen rule files the session loads on demand.
  Its size, its footer and its rule-file index are held by
  `testing/unit/docs/test_agents_constitution.py`.
- **The documentation site is published by CI** (ADR 0012): a push to `main` uploads the strictly
  built site as the Pages artifact and deploys exactly that artifact, in the system's own identity —
  the curator's palette, the mark and the favicon the SPA serves, and PT Serif self-hosted.

### Changed

- **One name per screen and one verb per action**: `lib/screens.ts` holds the label the menu, the
  settings card and the page's own `<h1>` all read, and `lib/copy.ts` holds the action catalogue, so
  the three cannot disagree. The subject vocabulary follows the contract — `gaveta` became
  `Categoria` and `cluster` became `agrupamento` — and `apagar`, `unificar`, `rung`, `apply`,
  `dry-run` and `undo` are retired, held out by a gate over every string that can reach a screen.
- **One width for every screen**: the per-screen caps had drifted — `max-w-5xl` on most,
  `max-w-4xl` on five, `max-w-6xl` on one — so two screens side by side stopped growing at different
  points. The column has no maximum now, and what keeps a cap is the content's own measure.
- **`TODO.md` retired** into the issues, the guides and the milestones: the roadmap page was a second
  list of what is left, and it drifted from the one the work is tracked in.

### Fixed

- **The attribution now reaches the screens before a session.** `AttributionFooter` returned before
  the shell existed, so the four §7(b) elements — and the version — were invisible to anyone without
  an account, which the component's own docstring already called wrong.
- **The rail no longer scrolls the menu out of view**: `min-h-full` made the rail as tall as the
  *page*, so on a long screen the whole menu left the viewport and the nav's `overflow-y-auto` never
  engaged. Measured at 1440x900 at the foot of a long screen: a blank rail column and no menu.
- **A retired word inside a template literal or a JSX node the formatter wrapped was invisible** to
  the copy pass *and* to the first version of its gate. The extractor reads both, and its own tests
  run on synthetic input so they cannot pin the copy of the day.

### Security

- **The first-run route is atomic, not merely guarded.** Measured against PostgreSQL 15:
  `INSERT … SELECT … WHERE NOT EXISTS` lets both concurrent transactions insert, because `NOT EXISTS`
  is a predicate over a snapshot and not a lock. The table lock is what makes the second call wait,
  insert nothing and answer 409 — and the predicate is that the table is **empty**, so deactivating
  an account cannot reopen the door.
- **CodeQL scans the workflows** as well as the code, and every action stays pinned to a resolved
  commit.

## [1.0.0] - 2026-10-08

### Added

- **The three-layer pipeline**: ingestion (scraping queue) → staging (typed ISAD(G) columns) →
  archive (the enriched description), with a content-addressed change key so a re-parse reaches the
  archive and an unchanged record does not.
- **Nine AI workers** with a single runner: `transfer`, `cleaning`, `ner`, `typology`, `thumbnail`,
  `conflict-judge`, `macro-category`, `quality-validator`, `embedding`. Each stamps a versioned key
  in a JSONB `execution_log`, so a worker is idempotent and a text change puts a record back in the
  queue.
- **Human-in-the-loop governance**: `HUMAN_APPROVED` blocks AI rewrites, a review queue holds
  tag × entity collisions, and every human edit records its before/after in a revision ledger.
- **Curation API and UI**: 95 paths / 112 operations, and 24 screens covering the collection, the
  arrangement, the subject and entity vocabularies, quality, the operations panel and the accounts.
- **Lexical and semantic search** with facets: an accent-insensitive generated `search_vector` with
  GIN indexes, and pgvector embeddings with an HNSW cosine index.
- **A public diffusion surface** (`/api/v1/public/*`) with a field-by-field projection and an exact
  partition test, gated on `is_published` and answering 404 — never 403 — for an unpublished record.
- **Authentication and authorization** (ADR 0009): first-party session cookie with only the SHA-256
  of the token in the database, argon2id passwords, three roles, and **every operation declaring its
  permission** with a partition test that fails when one is left unclassified.
- **Account administration**: `/api/v1/users` and the `Configurações › Usuários` screen — create,
  edit, deactivate, reset a password, and list or revoke the sessions of an account.
- **Local observability** (ADR 0005): `/health/live` and `/health/ready` for an orchestrator, a
  request id on every answer, and `/api/v1/system/failures` grouping both failure ledgers by a root
  cause computed in a generated column.
- **A generated, committed API contract**: `bun run contract` dumps the OpenAPI document and
  regenerates the TypeScript client; CI fails when either is stale.
- **The documentation an installer, an operator and an archivist read** (ADR 0010): four guides in
  English and Portuguese, plus the index and the ADRs, held to the code by two rules — coverage is a
  gate (a worker, a setting, a screen, a table or an ADR missing from the page that owns it fails the
  suite) and freshness is a report whose verdict lands in a triage ledger.
- **A release flow that produces verifiable artifacts**: the `Release` workflow validates the
  version, builds the curator SPA, generates the Python SBOM and attests the build provenance before
  creating the tag and the release.

### Changed

- **The language is code; the collection vocabulary is data** (ADR 0008): the Portuguese profile
  lives in `core/language`, and the arrangement names and collection terms are rows the archivist
  edits from a screen. An installation declares its own origin and vocabulary instead of inheriting
  the reference collection.
- **The AI text composition moved into SQL**: one expression feeds the embedding text, its MD5 stamp,
  NER and the typology, so the four cannot disagree.
- **Object storage is not shipped.** `docker compose up -d` starts PostgreSQL only; the project needs
  an S3-compatible endpoint (`S3_ENDPOINT_URL`) and does not care which product serves it, so the
  storage is infrastructure the operator brings rather than a service this repository runs.

### Fixed

- A description whose title was a placeholder (`não informado`) was **dropped** by staging, because
  cleaning turned the required title into `None`. It now falls back to `SEM TÍTULO`.
- Two merge defects in both vocabularies: deleting a tag before repointing its synonyms destroyed the
  spellings earlier merges had absorbed, and an undo restored the row without the links it created.
- A `Field(description=…)` on a field typed with a shared enum rewrote the enum's schema for the whole
  document, so the committed contract depended on `PYTHONHASHSEED` and CI failed at random.

### Security

- **Lockout with backoff**: failed sign-ins are counted in a column and written through their own
  committed session (the request transaction rolls back on the failure it would have counted), and
  only a *correct* password on a locked account is told the reason.
- **Per-address rate limiting** on the login route, in front of the per-account lockout.
- **Cross-origin checking** on mutating requests, allowing a same-origin `Origin` or one declared in
  `AUTH_TRUSTED_ORIGINS`, and never checking a read.
- **Known advisories in the runtime dependencies resolved** by minimal version bumps — `torch`,
  `transformers`, `sentence-transformers`, `setuptools`, `urllib3`, `pillow`, `anyio`, `multidict`,
  `soupsieve` and `fsspec` — instead of jumping every package to its latest release. The CI audit now
  reads the **runtime** export and not the development environment: an advisory in a tool that never
  reaches an installation no longer hides the ones that do.

[Unreleased]: https://github.com/CassioDalla/Scrinalia/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.1.0
[1.0.0]: https://github.com/CassioDalla/Scrinalia/releases/tag/v1.0.0
