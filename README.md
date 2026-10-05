# Memória Curitibana

A system for archivists to catalogue and manage archival descriptions (ISAD(G) metadata),
with AI-driven enrichment and Human-in-the-Loop governance.

The system ingests descriptions from a public archival source, normalises them through a
three-layer pipeline, and enriches them with named entities, typologies and subject
categories. Every AI decision is advisory: an archivist reviews and approves, and approved
documents are locked against further automatic rewrites.

> **Status:** research project under active development. The curator UI is a React SPA
> (`apps/curator/`) served by the API; the old Streamlit dashboard is still in the tree and is
> scheduled to be switched off. The HTTP API is the stable contract, and the TypeScript client
> is generated from it.

## How it works

Three layers, each one a domain under `src/memoria_curitibana/domains/`:

```
ingestion  ──►  staging  ──►  archive
(scraping       (structured,    (enriched document +
 queue)          cleaned data)   human review)
```

- **ingestion** — crawls the source site, keeps a queue of identifiers, and stores raw
  payloads with a content hash so re-runs stay idempotent.
- **staging** — parses the raw records into clean, typed ISAD(G) fields.
- **archive** — the curated record: the final document, the taxonomy (tags, entities,
  typologies), and the review status that governs who may still write to it.

Enrichment runs as independent workers over the archive layer:

```
transfer -> cleaning -> ner -> typology -> thumbnail -> conflict-judge -> macro-category
         -> quality-validator -> embedding
```

Each worker stamps a versioned key in the document's `execution_log`, so re-running a
worker only touches documents it has not already processed. The macro-category worker stamps
the **tag** (`archive_tags.execution_log`) instead, because it classifies the subject axis
rather than a document — and its stamp value is the **hash of the label set** it classified
against, so rewriting a curator label re-queues the affected tags by itself. The quality
validator grades the record (missing date, suspicious title, scope that was only boilerplate)
and sends it to human review, and the embedding runs last because every text mutation has to
happen before it.

The subject axis reads a **vocabulary** (`domains/archive/domain/vocabulary.py`), not the raw
tag list: eight drawers derived from the collection, plus two kinds of "this is not a subject"
— a deterministic guard for what has a recognisable form (a bare year, a placeholder, a street)
and the curated `domain_subject_exclusions` catalogue for the judgements no rule reaches.
Below 0.55 confidence a tag is left without a drawer **and** queued for review rather than
guessed at. A tag whose axis is provenance or geography (`ippuc`, `curitiba`) carries an
`archive_tag_facets` row instead of competing for a subject drawer.

## Requirements

- Python 3.12, managed with [`uv`](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/) 1.3+ (only for the curator UI)
- Docker (PostgreSQL/PostGIS and MinIO)
- For AI workers: a local [Ollama](https://ollama.com/) instance, and enough disk for the
  PyTorch and transformer model stack

## Getting started

```bash
# 1. Install dependencies (heavy: torch, transformers, spacy, bertopic)
uv sync

# 2. Configure the environment
cp .env.example .env      # then edit the values

# 3. Start the local infrastructure (PostGIS on 5432, MinIO on 9000/9001)
docker compose up -d

# 4. Create the schema
uv run alembic upgrade head

# 5. Run the API
uv run uvicorn main:app --reload
```

The API is then available at `http://localhost:8000/`, with the OpenAPI schema at
`/schema/swagger`.

### Curator UI

The archivist's interface is a React SPA in `apps/curator/`. It has no server of its own: Vite
proxies `/api` to the API in development, and in production the API serves the built files, so the
browser is always on the same origin and the project needs no CORS configuration.

```bash
bun install                                   # once per clone, from the repository root
bun run curator:dev                           # http://localhost:5173, proxies /api to :8000
bun run curator:build                         # writes apps/curator/dist, served by the API at /
```

The TypeScript client is **generated from the API contract**, never written by hand:

```bash
bun run contract          # dumps packages/api-contract/openapi.json and regenerates the client
```

CI fails when either artifact is stale, so a route or a schema change that is not accompanied by a
regenerated contract is caught at review time rather than in the browser.

### Dashboard (temporary)

The old Streamlit front end talks to the API over HTTP, so the API must be running:

```bash
uv run streamlit run src/memoria_curitibana/dashboard/app.py
```

## Running the workers

Prefer the unified runner, which exposes every worker behind one interface:

```bash
uv run python -m memoria_curitibana.domains.archive.workers.runner <name> \
    [--engine X --preset Y --batch N --option key=value]
```

Available names: `transfer`, `cleaning`, `ner`, `typology`, `thumbnail`, `conflict-judge`,
`macro-category`, `quality-validator`, `embedding`.
Each `worker_*.py` also carries an `execute(db, ...)` function and a `__main__` block, so a
single worker can be run directly while developing.

## Development

```bash
uv run pytest                 # full suite
uv run pytest -m unit         # fast tests, no database needed
uv run ruff check .           # lint
uv run ruff format .          # format
uv run basedpyright           # type check
uv run pre-commit install     # once per clone
```

Integration tests need a PostgreSQL database on port 5433:

```bash
docker compose -f docker-compose.test.yml up -d
```

> If something else already holds 5433 the container starts without publishing a port and the
> suite silently talks to the wrong database. Run with `TEST_DB_PORT=5434` and
> `TEST_DATABASE_URL=postgresql://test_user:test_password@localhost:5434/test_db`.

> The suite drops the schema on teardown. Do not serve the API against the test database
> while pytest is running; re-apply `alembic upgrade head` before starting a server again.

## Project layout

```
src/memoria_curitibana/   the application (installed package)
  api/                    Litestar controllers, request schemas, composition root
  core/                   settings, logging, database, unit of work
  domains/                ingestion, staging, archive (models/repository/services/workers)
  dashboard/              temporary Streamlit front end (to be removed)
apps/curator/             React SPA: the archivist's interface
packages/api-contract/    openapi.json, generated from the app and committed
testing/                  test suite (outside the package, on purpose)
migrations/               Alembic revisions; owns the database schema
docs/adr/                 accepted architecture decisions
main.py                   deployable entrypoint (re-exports the ASGI app)
```

## Documentation

- [`AGENTS.md`](AGENTS.md) — conventions and the architectural rules that are easy to get wrong
- [`TODO.md`](TODO.md) — roadmap
- [`docs/adr/`](docs/adr/) — architecture decision records
