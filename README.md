# Memória Curitibana

A system for archivists to catalogue and manage archival descriptions (ISAD(G) metadata),
with AI-driven enrichment and Human-in-the-Loop governance.

The system ingests descriptions from a public archival source, normalises them through a
three-layer pipeline, and enriches them with named entities, typologies and subject
categories. Every AI decision is advisory: an archivist reviews and approves, and approved
documents are locked against further automatic rewrites.

> **Status:** research project under active development. The Streamlit dashboard is a
> temporary interface and is scheduled to be replaced by a backend + React frontend; the
> HTTP API is the stable contract.

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
rather than a document. The quality validator grades the record (missing date, suspicious
title, scope that was only boilerplate) and sends it to human review, and the embedding runs
last because every text mutation has to happen before it.

## Requirements

- Python 3.12, managed with [`uv`](https://docs.astral.sh/uv/)
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

### Dashboard

The temporary Streamlit front end talks to the API over HTTP, so the API must be running:

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

> The suite drops the schema on teardown. Do not serve the API against the test database
> while pytest is running; re-apply `alembic upgrade head` before starting a server again.

## Project layout

```
src/memoria_curitibana/   the application (installed package)
  api/                    Litestar controllers, request schemas, composition root
  core/                   settings, logging, database, unit of work
  domains/                ingestion, staging, archive (models/repository/services/workers)
  dashboard/              temporary Streamlit front end
testing/                  test suite (outside the package, on purpose)
migrations/               Alembic revisions; owns the database schema
docs/adr/                 accepted architecture decisions
main.py                   deployable entrypoint (re-exports the ASGI app)
```

## Documentation

- [`AGENTS.md`](AGENTS.md) — conventions and the architectural rules that are easy to get wrong
- [`TODO.md`](TODO.md) — roadmap
- [`docs/adr/`](docs/adr/) — architecture decision records
