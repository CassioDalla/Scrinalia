-- Infrastructure extensions only. Table DDL is owned by Alembic migrations
-- (run `uv run alembic upgrade head` after the database is created).
--
-- pg_trgm powers the fuzzy-search GIN indexes; it is also created by the
-- initial migration so any Postgres instance can be provisioned from scratch.
-- postgis is kept for the app image in case geospatial features are added.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
