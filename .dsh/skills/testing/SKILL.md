---
name: testing
description: "The suite: what unit tests must never load, the Postgres test database and its traps, the fixtures and what CI runs."
whenToUse: "Before running, adding or debugging a test."
---

# testing

## The suite, the fixtures and the test database

- Unit tests never load real models. The `mock_registry` fixture monkeypatches `AVAILABLE_ENGINES`/`PRESETS` to shield any registry; do not call Ollama or an S3 endpoint in tests.
- Integration tests require the Postgres test database: `docker compose -f docker-compose.test.yml up -d` (port 5433, tmpfs in RAM, `pgvector/pgvector:pg15` — the same image CI uses). `testing/conftest.py` defaults to `postgresql://test_user:test_password@localhost:5433/test_db`; override with the `TEST_DATABASE_URL` env var. The compose file publishes `${TEST_DB_PORT:-5433}`, because 5433 is a popular host port: when another project already holds it the container starts **without publishing anything** and the suite silently talks to the wrong PostgreSQL, which looks like a test failure rather than a port conflict.
- The test schema is built by `Base.metadata.create_all`, **not** by Alembic. So `alembic upgrade head` against the test database is a trap: `create_all` then skips the tables it finds, the suite runs against the migrated schema instead of the models, and the result is hundreds of failures that read as regressions (measured: 53 failed + 42 errors, all gone after the tables were dropped). If you migrate the test database to run a server against it, drop the schema before running pytest again.
- Key fixtures in `testing/conftest.py`: `db_session` (SAVEPOINT + rollback per test), `use_test_db` (patches `scrinalia.core.database.get_db`, opt-in), `generate_archive_doc`, `generate_typology`, `mock_ner_engine`, `mock_staging_doc`, and `reference_vocabulary` (sows the collection vocabulary the tests carry as fixture data, from `testing/reference_vocabulary.py`). The last one exists because the test schema is built by `create_all`, which never runs a migration: a test that asserts the guard refuses a person's name has to declare that the collection carries it. The catalogue itself is **data of the installation** and does not ship — a fresh install starts empty and loads one with `python -m scrinalia.domains.archive.cli import`.
- Tests import the installed package (`scrinalia.*`), never a bare `core`/`domains`
  root, so the suite exercises the same boundary a consumer does. Because the source lives in
  `src/`, `uv sync` must have run at least once before pytest can import anything.
- CI (`.github/workflows/ci.yml`) carries the jobs that mirror a local run — a fast `uvx ruff` lint/format job; a `test` job that checks the committed `openapi.json` is current, then runs `alembic upgrade head` + `alembic check` and `uv run pytest` (which includes the documentation coverage gate) against a Postgres service on 5432; a `frontend` job (Bun) that regenerates the TypeScript client and fails on drift, then type-checks, lints and builds `apps/curator`; and a `docs` job that builds the site with `--strict` through `uvx` — plus the security and community jobs (`gitleaks`, `pip-audit`/`bun audit`, `zizmor`, DCO). The docs job checks out the **full history** on purpose: the freshness report is computed against git. Run the same checks locally before finishing.

