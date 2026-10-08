# Changelog

All notable changes to this project are documented here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) from its first release.

There is no release yet: everything below is what `main` carries today, and it will become
`v0.1.0` when the documentation cycle closes. Entries describe **behaviour**, not commits — the
history is the detail.

## [Unreleased]

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
- **Curation API and UI**: 94 paths / 111 operations, and 23 screens covering the collection, the
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

[Unreleased]: https://github.com/CassioDalla/Scrinalia/commits/main
