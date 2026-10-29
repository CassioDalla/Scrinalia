# Release fixtures for the migration test

`testing/integration/migrations/test_release_upgrade.py` applies the directory here to a scratch
database and runs `alembic upgrade head` against it. CI's own `alembic upgrade head` meets a
database the suite has just emptied; this one meets the catalogues and the rows a released
installation already has, which is the only way a backfill that assumes a null-free column fails
before an operator's upgrade does.

One directory per release, named after the version it is a snapshot of:

- `schema.sql` — `pg_dump --schema-only --no-owner --no-privileges` of a database migrated to the
  release, with the `\restrict`/`\unrestrict` lines `pg_dump` 15.19 wraps it in removed. They are
  psql meta-commands, not SQL, and psycopg2 rejects them; the test strips them too, so a freshly
  regenerated dump is usable before it is cleaned.
- `data.sql` — `pg_dump --data-only --inserts --no-owner --no-privileges` of the same database. It
  carries the rows the migrations seed, the release's `alembic_version` row, and the application
  rows below.

The test uses whichever directory is named in its `FIXTURE_DIR`, so a new release adds a directory
and moves that constant in the same pull request.

## Adding rows: the next data migration's job

A pull request that adds a data migration **adds the rows it touches to `data.sql` in the same pull
request**, with values that exercise the backfill (a null it must handle, a row it must keep, a row
it must change), and extends the assertions in `test_release_upgrade.py`. A fixture nobody extends
stops proving anything as soon as the next migration lands, which is exactly the failure this
directory exists to prevent.

The rows in the current fixture, and what they stand for:

| Table | Rows | Why it is there |
| --- | --- | --- |
| `auth_users` | an `ADMIN` with `locale = 'pt-BR'` and a `VIEWER` with `locale = 'en'` | the account row every per-user migration touches; the locale is the head migration's own column |
| `archive_documents` | a fund, a series and an item, with `parent_id` and the materialised `path` | the hierarchy and the review statuses (`PENDING_AI`, `HUMAN_APPROVED`, `NEEDS_REVIEW`) a backfill must preserve |
| `archive_tags`, `archive_document_tags` | three tags, two links | the subject axis and the join a merge/rename migration rewrites |
| `archive_entities`, `archive_document_entities` | one institution, one link | the entity axis, whose origin (`AI`, `HUMAN`, `UNKNOWN`) is its own enum |
| `raw_data`, `staging_documents`, `scraping_queue` | one row each for `fixture-item`, origin `csv` | the three layers in front of the archive, which the origin and transfer migrations walk |
| `archive_worker_runs` | one `ner`/`SUCCESS` row requested by the admin | the run ledger, which keeps a foreign key into `auth_users` |

The migration seeds are data too, and are part of the dump: six description levels, ten typologies,
eight macro categories and the `manual`/`csv` origins. A migration that rewrites the ladder or the
catalogues is verified against those rows.

## Regenerating a release fixture

Only when a release is cut (or when the fixture is first created for a previous release):

1. Create a scratch database in the test cluster, e.g.
   `docker exec scrinalia_db_test psql -U test_user -d test_db -c "CREATE DATABASE fixture_180"`.
2. From a checkout of the release tag, with `DB_*` pointing at that database, run
   `uv run alembic upgrade head` — the migrations must be the tag's, not `dev`'s.
3. Insert the application rows from the table above (raw SQL is enough; they are a handful).
4. Dump both files with the `pg_dump` of the same major version as the test image (15), e.g.
   `docker exec scrinalia_db_test pg_dump -U test_user --schema-only --no-owner --no-privileges fixture_180`,
   then the same with `--data-only --inserts`. Remove the `\restrict`/`\unrestrict` lines.
5. Run `TEST_DATABASE_URL=... uv run pytest testing/integration/migrations` and read the
   assertions: they name the values the fixture is supposed to carry.
