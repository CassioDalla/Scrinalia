# AGENTS.md

## About the project
A system for archivists to catalog and manage archival descriptions (ISAD(G) metadata), with AI enrichment (NER, zero-shot classification, clustering) and Human-in-the-Loop governance.

Three-layer pipeline, each layer a domain under `domains/`:
`ingestion` (scraping queue) -> `staging` (structured, cleaned data) -> `archive` (final enriched document + human review).

- API: Litestar in `main.py` (`api/controllers/`), NOT FastAPI.
- Front: Streamlit dashboard in `dashboard/`, **temporary** — the intent is to migrate to a backend + React frontend. Treat the API as the stable interface and avoid coupling new features to Streamlit.
- Code, docstrings, logs, and domain messages are in Portuguese; commits follow Conventional Commits.
- `README.md` is empty; the roadmap and architecture decisions live in `TODO.md`.

## Commands
Always run from the repo root. Python 3.12 managed by `uv` (`uv.lock`).

- Install deps: `uv sync` (heavy: `torch`, `transformers`, `spacy`, `bertopic`).
- API: `uv run uvicorn main:app --reload`.
- Dashboard: `uv run streamlit run dashboard/app.py` — requires the API running at `API_BASE_URL` (default `http://localhost:8000/`).
- Local infra: `docker compose up -d` (PostGIS on 5432 + MinIO on 9000/9001).
- Workers: prefer the unified runner — `uv run python -m domains.archive.workers.runner <name> [--engine X --preset Y --batch N --option key=value]`, where names are `transfer`, `cleaning`, `ner`, `typology`, `thumbnail`, `conflict-judge`. Pipeline order: `transfer -> cleaning -> ner -> typology -> thumbnail -> conflict-judge`. Each `worker_*.py` also has an `execute(db, ...)` + `__main__` block runnable directly.
- Database migrations: `uv run alembic upgrade head`; new revision: `uv run alembic revision --autogenerate -m "..."`; drift check: `uv run alembic check`.
- Tests: `uv run pytest`; a single test: `uv run pytest tests/unit/archive/workers/test_worker_ner.py::test_name`.
- Lint/format: `uv run ruff check .` and `uv run ruff format .` (ruff is a dev dependency; line-length 120, double quotes). CI enforces `ruff format --check .`.
- `Procfile` defines the `api` (`uvicorn` with `CUDA_VISIBLE_DEVICES=""`, i.e. CPU) and `web` (`streamlit`) processes.

## Database and infra
- Schema is owned by **Alembic** (`migrations/`, config in `alembic.ini`, connection URL from `core.config.settings`). Apply with `uv run alembic upgrade head`. The models in `domains/*/models/` are the single source of truth; `uv run alembic check` must report no drift.
- `db-init/*.sql` runs **only on first volume creation** and now provisions infrastructure only: extensions (`00-extensions.sql`) and the read-only `portal_reader` role (`01-public_reader_user.sql`). It no longer creates tables. Recreate the volume with `docker compose down -v && docker compose up -d`, then run the migration.
- GIN fuzzy-search indexes (`gin_trgm_ops`) require the `pg_trgm` extension: the initial migration creates it, and `tests/conftest.py` creates it before `create_all`.
- `.env` is gitignored. Keys in `core/config.py`: `DB_*`, `ARQDOC_*`, `PUBLIC_SCRAPE_*`, `S3_*`, `OLLAMA_HOST_URL`, `API_BASE_URL`. `docker-compose.yml` reads `DB_USER`/`DB_PASS`/`DB_NAME` (defaults admin/admin123/memoriacuritibana).
- Models are Postgres-specific (JSONB, ARRAY, native enums, GIN indexes) — they do not port to SQLite.

## Architecture conventions (easy to get wrong)
- DDD per domain: each domain has `models/`, `repository/`, `services/`, `schemas/`, `workers/`. Litestar controllers in `api/`; `api/dependencies.py` builds services per request by injecting the session.
- Domain services receive repositories via constructor (`TagService(repo, document_repo)`); do not instantiate a session inside business logic.
- AI engines are pluggable via `registry.py` in each subpackage (`engines/classification`, `engines/NER`, `engines/clustering`, `engines/LLMs`): `get_engine(engine_name, preset, **kwargs)`, where `kwargs` overrides the preset. Contracts live in `engines/base.py` (Protocols). To add an engine, register it in `AVAILABLE_ENGINES` and add a preset.
- Worker idempotency: each worker stamps a versioned key in the JSONB `execution_log` (`worker_ner_v1`, `worker_typology_classifier_v1`, `cleaning_rule_{id}`), and the pending query filters by that key's absence (GIN index `ix_archive_exec_log`). Every new worker must follow this pattern + `flag_modified`.
- `DocumentRepository.upsert_archive_document` is **exclusive to the staging->archive migration**. The `ON CONFLICT` only updates if `staging_content_hash` changed and the status is not `HUMAN_APPROVED`. AI workers must NOT use it (they use surgical updates); otherwise the AI data is discarded.
- Governance: `ArchiveReviewStatus` controls the lifecycle (`HUMAN_APPROVED` blocks AI rewrites); tag x entity conflicts go to `archive_ai_review_queue`.
- The dashboard is heterogeneous: `dashboard/services/search_service.py` queries Postgres directly via `get_db()`, while `taxonomy_api.py`, `cleaning_service.py`, and `entity_service.py` call the API via `requests`. Prefer the API for new features.

## Tests
- Unit tests never load real models. The `mock_registry` fixture monkeypatches `AVAILABLE_ENGINES`/`PRESETS` to shield any registry; do not call Ollama/MinIO in tests.
- Integration tests require the Postgres test database: `docker compose -f docker-compose.test.yml up -d` (port 5433, tmpfs in RAM). `tests/conftest.py` defaults to `postgresql://test_user:test_password@localhost:5433/test_db`; override with the `TEST_DATABASE_URL` env var.
- Key fixtures in `tests/conftest.py`: `db_session` (SAVEPOINT + rollback per test), `use_test_db` (patches `core.database.get_db`, opt-in), `generate_archive_doc`, `generate_typology`, `mock_ner_engine`, `mock_staging_doc`.
- Pytest uses `--import-mode=importlib`; tests import top-level packages (`core`, `domains`), so run pytest from the root.
- CI (`.github/workflows/ci.yml`) has two jobs: a fast `uvx ruff` lint/format job, and a test job that runs `alembic upgrade head` + `alembic check` and `uv run pytest` against a Postgres service on 5432. Run the same checks locally before finishing.
