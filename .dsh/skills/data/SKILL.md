---
name: data
description: "Schema, migrations, settings and logging: Alembic owns the schema and the extensions, the settings module and the loguru sinks."
whenToUse: "When adding a migration, a setting, an extension or a log sink."
---

# data

## Settings and logging

- `src/scrinalia/core/config.py` exposes typed settings (`pydantic-settings`) as the module-level `settings`; `get_settings()` is `lru_cache`d and `get_settings.cache_clear()` resets it in tests. Env vars win over `.env`. `DB_PASS`/`S3_*` are `SecretStr` — unwrap with `.get_secret_value()`. `DATABASE_URL` is a property and percent-encodes the credentials.
- `src/scrinalia/core/logger.py` owns the loguru sinks (`LOG_DIR`/`LOG_LEVEL` from settings). `configure_logging()` is idempotent and only calls `logger.remove()` on first run, so importing it never tears down sinks another host already added. Third-party logs (uvicorn, Litestar) reach the sinks through `InterceptHandler`; `asgi.py` wires the same handler into Litestar's `LoggingConfig` because Litestar and uvicorn both apply a `dictConfig` at startup.
- `src/scrinalia/core/database.py` builds the engine lazily (`get_engine()`/`get_session_factory()`/`create_session()`), so importing it never needs a live database. `get_db()` yields a session and leaves the transaction to the caller; the API owns its transaction through `provide_unit_of_work` in `api/dependencies.py`.

## Schema, migrations and the database

- Schema is owned by **Alembic** (`migrations/`, config in `alembic.ini`, connection URL from `core.config.settings`; `prepend_sys_path` is intentionally empty). Apply with `uv run alembic upgrade head`. The models in `src/scrinalia/domains/*/models/` are the single source of truth; `uv run alembic check` must report no drift.
- There is no `db-init` anymore. The schema **and** the extensions it needs are owned by Alembic: `pg_trgm` (fuzzy-search GIN indexes), `unaccent` (accent-insensitive full-text search) and `vector` (embeddings). Fresh volume -> `docker compose up -d` -> `uv run alembic upgrade head`. Recreate a clean volume with `docker compose down -v`.
- `testing/conftest.py` creates `pg_trgm`, `unaccent` + its `immutable_unaccent` wrapper and `vector` before `create_all` for the test database, because the test schema is built from the models and those columns/indexes depend on the extensions. Because the suite **drops the schema on teardown**, never run a server against the test database in parallel with pytest, and re-run `alembic upgrade head` before starting one again.
- The dev database is Alembic-managed. An older volume was found without `alembic_version` (schema created by `create_all`, drifting from the models in 43 places, which made every ORM read of a tag fail); it was rebuilt by copying the model tables into a database created with `alembic upgrade head` and renamed to `scrinalia_legacy`. If a database ever drifts again, do **not** point pytest at it (the conftest drops the schema): build a clean database, copy the data and verify with `alembic check`.
- `.env` is gitignored and `.env.example` is the annotated copy. `src/scrinalia/core/config.py` owns **32 fields**: `DB_*`, `PUBLIC_SCRAPE_*`, `ACERVO_SOURCE`, `ACERVO_LANGUAGE`, `S3_*`, `OLLAMA_HOST_URL`, the 14 `AUTH_*` (session cookie and lifetime, cookie `Secure`, argon2id cost, lockout and rate limit, trusted origins), `LOG_DIR`/`LOG_LEVEL`/`DEBUG` and `WORKER_RUNTIME_MAX_WORKERS`. The install guide is the table, and `testing/unit/docs/test_documentation_coverage.py` fails when a field is missing from it. `docker-compose.yml` reads `DB_USER`/`DB_PASS`/`DB_NAME` (defaults admin/admin123/scrinalia) and gives the **app container** its own `APP_OLLAMA_HOST_URL`, because an `environment:` entry wins over `env_file` — a `OLLAMA_HOST_URL=http://localhost:11434` in `.env` is correct for `uvicorn` on the host and wrong inside the container.
- Models are Postgres-specific (JSONB, ARRAY, native enums, GIN indexes) — they do not port to SQLite.

