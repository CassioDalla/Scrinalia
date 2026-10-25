---
sources:
  - .env.example
  - Dockerfile
  - Procfile
  - docker-compose.yml
  - docker-compose.test.yml
  - docker/entrypoint.sh
  - docker/postgres/Dockerfile
  - models/requirements.txt
  - package.json
  - pyproject.toml
  - src/scrinalia/core/config.py
  - src/scrinalia/core/database.py
  - src/scrinalia/domains/archive/workers/scheduler.py
  - src/scrinalia/core/database_cli.py
  - src/scrinalia/core/logger.py
  - src/scrinalia/core/storage.py
  - src/scrinalia/api/health_probe.py
  - src/scrinalia/api/system_health.py
  - src/scrinalia/api/controllers/health_controller.py
  - src/scrinalia/api/controllers/setup_controller.py
  - src/scrinalia/api/spa.py
  - src/scrinalia/domains/archive/workers/runner_daemon.py
  - src/scrinalia/domains/identity/cli.py
  - src/scrinalia/domains/ingestion/sources.py
  - apps/curator/src/components/layout/AppShell.tsx
  - apps/curator/src/components/layout/SetupForm.tsx
  - apps/curator/src/lib/screens.ts
  - apps/curator/src/lib/settings.ts
  - docs/adr/0004-worker-execution-from-the-api.md
  - docs/adr/0009-authentication-and-authorization.md
  - docs/adr/0014-the-workers-leave-the-api.md
  - docs/adr/0011-first-run-setup-without-an-open-door.md
---

# Installing and deploying

Scrinalia is installed by the institution that keeps the collection, on its own infrastructure, and
runs there without a hosted service. This page is the ordered sequence for a third-party
installation: what has to be installed, which variable changes what, and the operations the
deployment owns afterwards. It describes the code as it ships.

The operator reads this page; the archivist's screens are in [Curation](curate.md) and the worker
pipeline is in [Operations](operate.md).

## What you are installing

The installation is four pieces. Only the first two are in this repository.

| Piece | Runs as | Where it comes from |
| --- | --- | --- |
| API and curator UI | one process (`uvicorn`, one worker) | this repository |
| PostgreSQL 15 with `pgvector` | a container or a server you manage | `docker-compose.yml` builds one; a stock server works if it has the extension |
| S3-compatible object storage | any endpoint speaking S3 | **you bring it** — see [Object storage is not shipped](#object-storage-is-not-shipped) |
| Ollama host | a server serving the LLM models | **you bring it**; only the Ollama-backed engines need it |

## Prerequisites

### Software

| Requirement | Version used here | Why |
| --- | --- | --- |
| Docker Engine with the Compose v2 plugin (`docker compose`) | Docker 29.1.3, Compose 2.40.3 | PostgreSQL comes from `docker-compose.yml`, which pins the project `name:` and uses the `env_file: {path, required: false}` form — the Compose implementation has to accept it |
| [`uv`](https://docs.astral.sh/uv/) | 0.11.14 | manages Python 3.12 and the lockfile; the `Dockerfile` pins the `uv` image to 0.11.14 |
| [Bun](https://bun.sh/) | 1.3.14 | installs the front-end workspace and runs `curator:build`; Bun manages packages and scripts, Vite bundles (ADR 0003) |
| Python | 3.12 | `requires-python = ">=3.12"`; `uv` provides it, no system Python is needed |

The versions above are the ones the repository was built and checked against; a newer patch release
of any of them is expected to work. All commands in this page run from the repository root.

### Disk

The Python environment and the model caches are the large items. Measured in a working checkout:

| What | Measured | Command |
| --- | --- | --- |
| Python environment (`.venv`), including torch, transformers, spaCy and the 602 MB `pt_core_news_lg` model | 6.6 GB | `du -sh .venv` |
| Hugging Face model cache after the first classification and NER run | 4.6 GB | `du -sh .cache-hf` |
| Front-end dependencies | 268 MB | `du -sh node_modules` |
| Ollama models (the presets name `gemma4:e4b`) | not measured | fetched by Ollama, not by this repository |
| PostgreSQL data | depends on the collection | grows with the descriptions, not with the software |

Plan for roughly 12 GB free for the Python stack, the model cache and the front-end dependencies,
plus room for the database. If you also build the container image, add the image itself — the
`Dockerfile` notes its virtualenv alone is about 6 GB.

### Memory

**This page does not state a minimum RAM, because it was not measured.** As a reference for what was
observed while writing it: the development host reports 15 GiB total and 8.3 GiB available
(`free -h`). The memory a run needs is driven by the models held in the process — the classification
and NER engines load a transformer or a spaCy pipeline each — and by Ollama holding its own model at
the same time. Measure on the target machine with the model loaded before sizing a server; a machine
that is comfortable for the API can still be short for a worker run.

### External services

- A PostgreSQL 15 server with `pgvector`. Alembic creates the extensions the schema needs
  (`pg_trgm`, `unaccent`, `vector`), but it cannot install the extension *packages*: on a stock
  PostgreSQL without pgvector, `alembic upgrade head` fails at the embeddings migration. The image
  in `docker/postgres/Dockerfile` starts from pgvector and adds PostGIS, so both are available;
  PostGIS is installed but not enabled by any migration yet.
- An S3-compatible endpoint reachable from the API process, with a bucket that **already exists**.
- An Ollama host, if you will use the Ollama-backed engines. `OLLAMA_HOST_URL` is where every
  preset-backed engine resolves its host; `http://localhost:11434` is the fallback when it is unset.

## The runner and the API

The API only enqueues since ADR 0014; a runner outside it executes the workers. That is why the API
can run with `uvicorn --workers N` — there is no background executor and no start-up recovery in it —
and why the workers need a second process, started from the repository root or the image:

```bash
uv run python -m scrinalia.domains.archive.workers.runner_daemon \
    --name gpu-01 --workers ner,typology,embedding
```

`--workers` narrows what the runner accepts (the default is the whole catalogue); `--concurrency`,
`--heartbeat-seconds`, `--lease-seconds`, `--poll-seconds`, `--sweep-seconds`, `--once` and
`--drain-seconds` are in the [Operations guide](operate.md#the-runner). The runner claims a `QUEUED`
row with `FOR UPDATE SKIP LOCKED`, renews a lease while it runs and records the effective
configuration. It refuses a schema behind its code: apply the API's migrations first. The panel shows
the runner and whether it accepts each worker; a run enqueued with no online runner waits.

The database is the only channel between the API and a runner: the API never calls one.

The scheduler (ADR 0015) is a third process, separate on purpose: it turns each worker's agenda into
`QUEUED` rows and never executes one. `python -m scrinalia.domains.archive.workers.scheduler` takes an
advisory lock, so one instance at a time is the database's decision; the compose `scheduler` service
and `bun run scheduler:dev` start it. The API, the runner and the scheduler can each live on their own
machine, and only the scheduler writes the schedule table.

## The network and the credential

A runner on another machine reaches the same PostgreSQL. Two things make that safe:

1. **A private path.** WireGuard/Tailscale, or an SSH tunnel on the runner host
   (`ssh -N -L 5432:localhost:5432 user@vps`), with `pg_hba.conf` accepting only `hostssl` from that
   path; never expose `5432` publicly.
2. **TLS.** `DB_SSLMODE` (default `prefer`) is appended to the derived DSN; a remote database sets
   `verify-full` with a CA. A full `RUNNER_DATABASE_URL` can carry its own host and `sslmode`, so the
   runner does not depend on the API's DSN.

The least-privilege role is optional hardening. It keeps the runner out of the identity tables while
it keeps writing the archive, which is what a worker does:

```sql
CREATE ROLE scrinalia_runner LOGIN PASSWORD '<secret>';
GRANT CONNECT ON DATABASE <db> TO scrinalia_runner;
GRANT USAGE ON SCHEMA public TO scrinalia_runner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO scrinalia_runner;
REVOKE ALL ON auth_users, auth_sessions FROM scrinalia_runner;
GRANT SELECT ON alembic_version TO scrinalia_runner;
REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM scrinalia_runner;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO scrinalia_runner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO scrinalia_runner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO scrinalia_runner;
```

Then set `RUNNER_DATABASE_URL=postgresql+psycopg2://scrinalia_runner:<secret>@<host>:5432/<db>?sslmode=verify-full`
in the runner's environment. Nothing else changes: the API keeps `DB_*`.

## Install: the ordered sequence

### 1. Get the code and declare the environment

```bash
git clone <repository-url> scrinalia
cd scrinalia
cp .env.example .env
# edit .env for your infrastructure
```

`.env` is gitignored. `Settings` reads it (`env_file=".env"`), a real environment variable wins over
it, and `docker compose` reads the same file for its interpolation. Start from `.env.example`, but
read [how the two files line up](#envexample-and-coreconfigpy) — nothing there needs changing.

### 2. Start the database

```bash
docker compose up -d
```

This starts PostgreSQL 15 on port 5432 and nothing else. The application service sits behind the
`app` profile, so this command never builds or starts it.

### 3. Install the Python environment

```bash
uv sync
uv pip install --python .venv/bin/python --require-hashes -r models/requirements.txt
```

Heavy: `torch`, `transformers`, `spacy` and `bertopic` are in the default dependency set. The second
command installs `pt_core_news_lg`, the 542 MB Portuguese pipeline the NER engine loads. It is
deliberately **not** in `uv.lock`: as a URL source, it made every `uv lock` download the wheel, and
Dependabot's update job died on that download before it reached the package it was updating (the
measurement is in the comment at the top of `models/requirements.txt`). `uv sync` is exact and prunes
what the lock does not name, so run the second command again after any `uv sync`.

### 4. Create the database and the schema

```bash
bun run db:init
```

`db:init` is those two steps in one: it brings the container up, creates the database `DB_NAME` names
when it is not there yet, and applies the schema. Repeating it is harmless — it is idempotent. It is
also what recovers a database that was dropped from an existing volume, the case `docker compose up
-d` cannot recover alone: `POSTGRES_DB` is honoured when the volume is *initialised*, so a database
deleted afterwards stays deleted and the migration fails on a database that is not there.

The schema itself is owned by Alembic and nothing else creates it. `uv run alembic upgrade head`
applies it, and the same command creates the `pg_trgm`, `unaccent` and `vector` extensions the schema
depends on. Confirm the result with `uv run alembic check`, which reports no drift on a healthy
installation.

The order matters: this step needs a reachable database, which is why the container comes first. To
throw everything in that database away and start from an empty one, `bun run db:recreate` prints what
it would destroy and asks for the database name before dropping it. Where nobody can type it — a
provisioning script — the same operation is `uv run python -m scrinalia.core.database_cli recreate
--yes`; `bun run` does not forward extra arguments to a composed script, so the flag has to go to the
module. It is database-scoped on purpose: `docker compose down -v` destroys the whole volume — every
sibling database in it — and is the only way to get a *fresh* volume, where `POSTGRES_DB` is honoured
again.

### 5. Build the curator UI

```bash
bun install
bun run curator:build
```

`bun install` runs once at the repository root (it is a workspace). The build writes
`apps/curator/dist`, and `create_app()` mounts that directory at `/` when it exists — which is what
keeps the browser on the same origin as the API and the project free of CORS. Without the build the
API still answers; it just serves no UI.

### 6. Create the first administrator

An empty installation has two doors to the same account: the first-run screen in the UI, or the CLI
on the host. Each creates an `ADMIN` whose password somebody chose, and only the first door closes
behind it — the first-run route answers 409 forever once an account exists, while the CLI is host
administration and still creates accounts at any time.

```bash
uv run python -m scrinalia.domains.identity.cli create \
  --email voce@instituicao.org --name "Seu Nome" --role ADMIN
```

The CLI is the path that works before the API is running, and the one a headless install uses.
Without `--password` it generates one, prints it, and marks the account **temporary**, so the
password in the terminal's scrollback stops being a credential — the account replaces it at the
first sign-in. The roles are `ADMIN`, `CURATOR` and `VIEWER`, and the CLI also has `list`,
`reset-password`, `activate`, `deactivate` and `set-role`.

Once the API is up (step 7), an installation whose `auth_users` is still empty answers the first
visit with **Primeiro acesso da instalação** instead of the sign-in form: e-mail, name and the
password, asked twice. It creates the first `ADMIN` and signs that person in, so there is no second
sign-in and no temporary password. The screen asks `GET /api/v1/setup/status`, which is public
because an installation with no accounts has no secret to protect. The card carries the product's
logomark at its top, the same plate the sign-in card has: this is the first screen an installer sees,
and it is the one place the name is worth showing in full.

The first-run route closes **forever** after the first account exists — deactivated or not, because
the predicate is that the table is empty, and a rule a deactivation could reopen would be a way back
to an open door. The CLI is not a door the installation closes: it runs on the host with the same
service the API uses and still creates accounts afterwards. Until then, whoever reaches the instance
first can create that account;
`POST /api/v1/setup/admin` is serialized by a table lock so two simultaneous attempts cannot both
succeed, but the lock cannot close the window (ADR 0011). **Configure the instance before exposing
it.**

### 7. Start the API

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

The API is then at `http://localhost:8000/`, the UI at the same address and the OpenAPI document at
`/schema/swagger`. `--reload` belongs to development (`bun run api:dev`), not to an installation.
Before exposing the instance, set `AUTH_COOKIE_SECURE` — see [HTTPS](#https).

## Environment variables

Every setting is defined once in `src/scrinalia/core/config.py` (`Settings`). All of them have a
default, so the API boots with an empty `.env`; what fails fast without configuration is the
pipeline, not the boot — `ACERVO_SOURCE` is required by the staging transform and
`PUBLIC_SCRAPE_*` by the ingestion adapter.

| Variable | Default | What it changes |
| --- | --- | --- |
| `DB_USER` | `admin` | database user; must match the server or the `db` service |
| `DB_PASS` | `admin123` | database password; a secret, unwrapped only where the driver needs it |
| `DB_HOST` | `localhost` | database host: `db` inside the compose network, the server's address on bare metal |
| `DB_PORT` | `5432` | database port |
| `DB_NAME` | `scrinalia` | database name; the compose service creates it on first boot |
| `DB_SSLMODE` | `prefer` | libpq transport appended to the derived DSN; `verify-full` with a CA when the database is reached across a network |
| `RUNNER_DATABASE_URL` | unset | the external runner's own DSN (a secret); when unset it uses `DB_*`. It lets a GPU host hold a least-privilege role and its own `sslmode` (ADR 0014) |
| `PUBLIC_SCRAPE_URL` | unset | base URL of the source site the ingestion worker lists; required to scrape |
| `PUBLIC_SCRAPE_DETAIL_URL` | unset | detail-page URL prefix the ingestion adapter builds each record from; required to scrape |
| `ACERVO_SOURCE` | unset | names the active origin — the field labels the staging transform reads and the ports the scrape builds; the only one shipped is `pmc`, `--origin` overrides it for one run, and there is **no default**: a staging run fails fast without it |
| `DEFAULT_TIMEZONE` | `America/Sao_Paulo` | the zone a worker's schedule is evaluated in when the operator does not name one; the cron runs here, not in the server's zone (ADR 0015) |
| `ACERVO_LANGUAGE` | `pt-BR` | selects the language profile — stopwords, date grammar, plural rules, the full-text dictionary and the spaCy model. The full-text dictionary reaches a generated column, so changing it is a **migration**, not a restart |
| `S3_ENDPOINT_URL` | unset | the S3-compatible endpoint (MinIO, Ceph, SeaweedFS, a cloud bucket); from a container, `localhost` is the container itself |
| `S3_BUCKET_NAME` | unset | the bucket the thumbnails go to; the worker confirms it once, before the run |
| `S3_ACCESS_KEY` | unset | credential with read/write on the bucket; a secret |
| `S3_SECRET_KEY` | unset | credential secret; a secret |
| `S3_AUTO_CREATE_BUCKET` | `false` | whether the worker may create `S3_BUCKET_NAME` when it is missing; off refuses the run with the command that creates it |
| `OLLAMA_HOST_URL` | unset → `http://localhost:11434` | the Ollama host every preset-backed engine resolves; an explicit `--option host=...` still wins |
| `AUTH_SESSION_COOKIE_NAME` | `scrinalia_session` | name of the first-party session cookie |
| `AUTH_SESSION_TTL_MINUTES` | `720` | how long a session lives; sliding, pushed forward by activity |
| `AUTH_SESSION_TOUCH_MINUTES` | `15` | how long a session may sit idle before its expiry is pushed forward |
| `AUTH_COOKIE_SECURE` | `false` | adds `Secure` to the session cookie; **set it `true` behind HTTPS** — see [HTTPS](#https) |
| `AUTH_PASSWORD_MIN_LENGTH` | `12` | minimum password length, enforced in the domain so the CLI obeys it too |
| `AUTH_PASSWORD_MEMORY_KIB` | `65536` | argon2id memory cost (64 MiB); raising it does not invalidate existing hashes |
| `AUTH_PASSWORD_TIME_COST` | `3` | argon2id iterations |
| `AUTH_PASSWORD_PARALLELISM` | `4` | argon2id lanes |
| `AUTH_LOGIN_MAX_ATTEMPTS` | `5` | failed sign-ins that lock an account |
| `AUTH_LOGIN_LOCKOUT_MINUTES` | `15` | first lockout window; each further lockout doubles it up to the ceiling |
| `AUTH_LOGIN_LOCKOUT_MAX_MINUTES` | `240` | ceiling of the lockout window, so a guesser has no fixed retry schedule |
| `AUTH_LOGIN_RATE_MAX` | `20` | sign-in attempts allowed per client address in the window; a process-local brake, not the durable defence |
| `AUTH_LOGIN_RATE_WINDOW_SECONDS` | `300` | the window those attempts are counted over |
| `AUTH_TRUSTED_ORIGINS` | empty | extra origins accepted on a mutating request, comma-separated; needed when a reverse proxy rewrites `Host` |
| `LOG_DIR` | `logs` | directory of the loguru sinks (`critical.log`, `ui_stream.jsonl`); created if missing |
| `LOG_LEVEL` | `INFO` | console and structured-stream level |
| `DEBUG` | `false` | reports the debug flag on the system diagnostic; it is shown, not used to switch logging |

`DATABASE_URL` is **not** in this table: it is a derived property that percent-encodes the
credentials from `DB_*`, not a value you set. It also appends `sslmode` from `DB_SSLMODE`.

### `.env.example` and `core/config.py`

They line up, and the check is worth knowing: every name in `.env.example` is a field of `Settings`
**except one**. `APP_OLLAMA_HOST_URL` is not a setting — it exists only for the container, where
`docker-compose.yml` maps it onto `OLLAMA_HOST_URL`, because an `environment:` entry wins over
`env_file`. It is explained under [Deploying the container image](#deploying-the-container-image).

`DB_NAME` is `scrinalia` in all three places — `core/config.py`, `.env.example` and the compose
interpolation. That is deliberate rather than cosmetic: the name used to be the reference
collection's database name, which made a fresh clone default to somebody else's catalogue, the same
defect ADR 0008 removed one layer up. A deployment that wants another name sets it in its own
`.env`, where its own configuration belongs.

## CPU and GPU

CPU is the shape the shipped process assumes, not a limitation of the code, and it is enforced in two
places. `pyproject.toml` points `torch` at the **CPU-only PyTorch index**, so no CUDA runtime is
installed at all; and `Procfile` starts the API as `CUDA_VISIBLE_DEVICES="" uv run uvicorn main:app
--reload`, with the runtime stage of the `Dockerfile` setting the same variable as an `ENV`, so the
process cannot see a GPU even on a host that has one.

The index is worth more than it looks. Measured on this lock, the default wheel resolves **3.46 GB**,
of which **2.19 GB are `nvidia-*` packages** and 248 MB `triton` — a runtime a CPU process never
executes, downloaded and cached by every installation and by CI. With the CPU index the same lock
resolves to **0.66 GB**. The variable covers the other direction: it keeps a re-locked CUDA
installation from failing on a host without the NVIDIA driver, and it hides the GPU from the parts of
the stack that reach CUDA by another route (`spaCy` only reaches one through `cupy`, the `spacy[gpu]`
extra, which this project does not declare).

To use a GPU instead, the wheel has to be there first:

1. Remove the `torch = { index = "pytorch-cpu" }` line and the `[[tool.uv.index]]` block for
   `pytorch-cpu` from `pyproject.toml`, then run `uv lock && uv sync`. The default PyPI wheel carries
   the CUDA runtime on Linux and Windows; macOS keeps its own build either way.
2. Do not set `CUDA_VISIBLE_DEVICES=""` for the process; start it without the variable, or name the
   device you mean (`CUDA_VISIBLE_DEVICES=0`).
3. Choose a configuration that uses the GPU. The typology engine (also used by the macro-category
   worker) has a `gpu_cloud` preset with `device: "cuda"`; NER's default preset is already `gpu`,
   which calls `spacy.prefer_gpu()` — note that spaCy reaches the GPU only through its CUDA runtime
   (`cupy`, the `spacy[gpu]` extra), which this project does not declare, so install it separately
   if you want the entities on the GPU; the embedding engine has a single `multilingual_minilm`
   preset on `device: "cpu"` and takes an override.
4. Run the runner on that host with the CUDA build, and let it accept the workers that use the
   model. The panel enqueues and the GPU runner claims; for a one-off on the host, the unified CLI is
   still there:

```bash
CUDA_VISIBLE_DEVICES=0 uv run python -m scrinalia.domains.archive.workers.runner_daemon \
    --name gpu-01 --workers ner,typology,embedding
CUDA_VISIBLE_DEVICES=0 uv run python -m scrinalia.domains.archive.workers.runner typology --preset gpu_cloud
```

The consequence that matters now: **the process that runs a worker is the runner, not the API**. A run
triggered from the panel executes on whichever runner claims it, with that runner's environment and
CUDA build; the API's `CUDA_VISIBLE_DEVICES=""` only hides the GPU from the API process. The effective
configuration still follows `explicit argument > persisted override > signature default`, so a preset
chosen in the panel is what the runner resolves — [Operations](operate.md) owns that precedence.

## HTTPS

Set `AUTH_COOKIE_SECURE=true` when the instance is reached over HTTPS, and only then.

The session is a first-party cookie whose row lives in `auth_sessions`; the server stores only the
SHA-256 of the token. With `AUTH_COOKIE_SECURE` left at its default `false`, the `Secure` attribute
is absent, so the browser will also send the cookie over plain HTTP — over an open network the
session token travels in clear text and can be read from the wire. That is what the flag prevents.

The default is `false` on purpose, and it is the reason a LAN installation over `http://` must not
turn it on: the browser drops a `Secure` cookie over plain HTTP **silently**, so the login would
look like it worked while nothing was stored, and the next request would be anonymous again. The
failure mode of getting this backwards is a login that appears to succeed and never sticks
(ADR 0009).

`AUTH_TRUSTED_ORIGINS` is the companion setting. Mutating requests are checked against their
`Origin`: same-origin is accepted by comparing the origin's authority with the request `Host`, and a
reverse proxy that rewrites `Host` makes every mutation look cross-origin unless the public origin
is listed there, comma-separated. Reads are never checked, and a request with no `Origin` (curl, the
CLI) is accepted. Because the API serves the UI from its own origin there is no CORS configuration
to write; forward the original `Host` through the proxy, or declare the public origin here.

## Deploying the container image

The container is the alternative to the bare-metal sequence above, and it packages what the code
already assumes: one image containing the API **and** the curator UI, plus a second service for the
runner.

```bash
docker compose --profile app up -d --build   # API + runner + PostgreSQL
docker compose --profile app logs -f app
docker compose --profile app logs -f runner
docker compose --profile app logs -f scheduler
# → http://localhost:8000
```

The `app` service is behind the `app` profile on purpose, so `docker compose up -d` — and therefore
`bun run dev` — keeps starting the infrastructure alone.

The profile also carries a `runner` service and a `scheduler` service: the same image, no published
port, the worker module as the runner's entrypoint and the scheduler module as the scheduler's. It is the CPU shape of a single-host installation; a GPU host runs the image on that
machine with a CUDA build and a private path to the database, as in [the network and the
credential](#the-network-and-the-credential). The API never calls it.

What the entrypoint does for you:

- `docker/entrypoint.sh` runs `alembic upgrade head` before the server starts, retrying while the
  database is unreachable and giving up with a non-zero exit after `SCRINALIA_DB_WAIT_SECONDS`
  (default 60). Set `SCRINALIA_RUN_MIGRATIONS=false` when migrations are a separate step, or when
  several replicas start at once: Alembic takes no distributed lock, so concurrent runs race. The
  `runner` service deliberately does **not** use this entrypoint: the API owns the migrations, and
  the runner checks the schema and retries instead of racing them.
- The runtime command is `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1` (the entrypoint
  keeps one process; the API now supports more, and a replica count is an operator's choice), and the
  image's own `HEALTHCHECK` reads `/health/live`, which touches nothing.

Configuration inside the container:

- The compose `environment:` block re-points `DB_HOST` at the `db` service and defaults
  `S3_ENDPOINT_URL` to `http://host.docker.internal:9000`.
- `OLLAMA_HOST_URL` **inside the container** is set from a different variable:
  `OLLAMA_HOST_URL: ${APP_OLLAMA_HOST_URL:-http://host.docker.internal:11434}`. A compose
  `environment:` entry wins over `env_file`, so setting `OLLAMA_HOST_URL` in `.env` does not reach
  the application container — set `APP_OLLAMA_HOST_URL` as well. That name is a Compose
  interpolation variable, not a `Settings` field; it exists only for this file. Confirm what the
  container will actually receive with `docker compose --profile app config`, which resolves the
  interpolation before anything starts.
- Volumes `pgdata`, `app_logs` and `hf_cache` survive a rebuild: the database, the loguru sinks
  (`LOG_DIR`) and the Hugging Face cache the models are downloaded into. The UI bundle comes from the
  build stage, never from the host: `apps/curator/dist` is gitignored and is excluded from the build
  context.

The first administrator is created from inside the container:

```bash
docker compose --profile app exec app \
  python -m scrinalia.domains.identity.cli create \
  --email voce@instituicao.org --name "Seu Nome" --role ADMIN
```

It does not have to be: with the container already serving the UI, an installation that still has no
account answers the first visit with the first-run screen (step 6), and the account created there is
the same one. The `exec` above is the path that also works when nothing is reachable yet.

### `docker-compose.test.yml` is not for production

`docker-compose.test.yml` describes the **test** database and nothing else: user `test_user`,
database `test_db`, the data directory on `tmpfs` (in RAM, so it is lost when the container stops),
and a published port `${TEST_DB_PORT:-5433}`. Its schema is built by `Base.metadata.create_all` in
`testing/conftest.py`, not by Alembic, and the suite drops it on teardown. Never point an
installation at it, and never run `alembic upgrade head` against it: `create_all` then skips the
tables it finds, the suite runs against a migrated schema instead of the models, and the result
reads as a regression rather than as the mistake it is.

## Object storage is not shipped

`docker compose up -d` starts PostgreSQL and nothing else. The project needs an S3-compatible
endpoint and does not care which product serves it — MinIO, Ceph, SeaweedFS or a cloud bucket are
infrastructure the operator brings, not something this repository ships.

The settings are `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` and
`S3_AUTO_CREATE_BUCKET`; the client is boto3 with signature v4. Two requirements come from the code:
the credentials need read/write on the bucket, and the bucket has to exist — the worker confirms it
once, before it touches the queue, and creates it only when `S3_AUTO_CREATE_BUCKET=true`. From
inside the `app` container `localhost` is the container itself, so point the endpoint at the
service's address on your network (`host.docker.internal` reaches a service running on the host).

The confirmation is deliberate, and it is what makes the failure legible. An endpoint does not
always say "this bucket does not exist": SeaweedFS answers **`AccessDenied`** to an upload into a
bucket that was never created, so every document of the run looks like a credential problem. With
the flag off (the default) the worker refuses the run up front, naming the bucket and the command
that creates it; with the flag on it creates the bucket and proceeds. `GET /api/v1/system/health`
reports the same distinction and never creates anything — a probe that provisions is a write hiding
in a read.

What lives there today is the `thumbnail` worker's JPEGs, under `thumbnails/`. The database stores
the resulting `s3://bucket/key` reference in `storage_thumbnail_uri`.

## Backup and restore

Two pieces of state, and only two: the database and the bucket.

Database dump and restore, using the `DB_USER`/`DB_NAME` you configured (`admin`/`scrinalia` by
default):

```bash
# dump, custom format
docker exec scrinalia_db pg_dump -U admin -d scrinalia -Fc > scrinalia-$(date +%F).dump

# restore into a fresh database, leaving the current one intact
docker exec scrinalia_db createdb -U admin scrinalia_restore
docker exec -i scrinalia_db pg_restore -U admin -d scrinalia_restore < scrinalia-2026-10-08.dump
# then point DB_NAME at scrinalia_restore and start the API
```

Bucket: copy it with whatever the provider gives you; any S3 client works, and the generic form is
`aws s3 sync --endpoint-url <url> s3://<bucket> ./bucket-backup`.

Restore the two **as a pair**. This is the trap: the `thumbnail` worker's queue is
`storage_thumbnail_uri IS NULL`, so a database restored without its bucket has every reference set
and no object behind it. The worker will not re-upload anything — the queue is empty — and the UI
serves broken images. Back them up together and restore them together.

### What is not recoverable

- Nothing beyond those two pieces, and the sentence is literal: the application keeps no other
  state. `LOG_DIR` (`logs/`) is operational history rather than archival record, the Hugging Face
  cache and `apps/curator/dist` are rebuildable, and the schema comes from `migrations/` in the
  repository. Keep a copy of your `.env` with the dump; it is not inside it, and a restore without it
  points at the defaults.
- **Everything written between the last dump and the failure.** The project configures no continuous
  archiving or WAL shipping; the recovery point is the dump.
- **A deleted description.** `DELETE /api/v1/documents/{id}` is the one operation that removes a
  record. It snapshots the whole row into `archive_document_deletions` — reference code, title,
  level, the full ISAD(G) payload, who deleted it and why — but the `Acervo › Excluídas` screen is a
  trail, not a recycle bin: there is no restore. A node with children is refused outright, because
  the self-referencing foreign key is `RESTRICT`.
- **Thumbnails, if the bucket is lost.** The database still names them, and the worker could
  re-derive one from `original_thumbnail_url` while the origin site still serves the image — but it
  will not, because the queue only contains documents whose `storage_thumbnail_uri` is `NULL`.
  Re-deriving them is a deliberate operation, not something the next run does by itself.
- The Ollama models and the Hugging Face cache are downloads, not state: they can be fetched again,
  which costs time and bandwidth, not data.

## Minimum operations

### Three health answers, three questions

| Endpoint | Question it answers | What it touches | Answer | Access |
| --- | --- | --- | --- | --- |
| `GET /health/live` | is the process answering? | nothing | 200 while the process answers | none |
| `GET /health/ready` | may this instance receive traffic? | one `SELECT 1` on its own engine | 200, or **503** when the database does not answer | none |
| `GET /api/v1/system/health` | which piece is down? | table counts, Ollama `/api/tags`, a bucket `HEAD`, the effective process configuration | 200 either way, with one verdict per piece | `OPERATE` permission (ADMIN) |

The two probes sit outside `/api/v1` and outside the OpenAPI document on purpose, so an orchestrator
does not have to know the API version. Do not merge them: a liveness probe that consulted the
database would make the orchestrator restart the API every time the database restarted. The human
panel is the third question and the expensive one, and it is the one that names the broken piece;
in the UI it is `Configurações → Operação → Saúde do sistema`.

### `/health/ready` answers 503

The process is alive and the database did not answer a trivial query. The readiness probe owns a
dedicated engine with a 2-second `connect_timeout` and `statement_timeout` and no pooled connection,
so the answer comes back quickly and cannot be inherited from a stale connection; the failure detail
goes to the log rather than the response body, because the route is unauthenticated and a connection
error echoes host and port. Check that the `db` service is running (`docker compose ps`), that
`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASS`/`DB_NAME` point at it, and that PostgreSQL accepts
connections. Restarting the API is the wrong reflex: the process is fine.

### Ollama is down

`GET /api/v1/system/health` reports `ollama.ok = false` with the host it used, whether that host
came from `OLLAMA_HOST_URL` or from the default, and the models the presets require next to the ones
the server has — so the missing list is the fix list. Only the Ollama-backed engines are affected:
the tag × entity judge (`conflict-judge`, default preset `gemma_4b_local`), the quality validator,
which takes its engine from the active `LLM_CHECK` cleaning rule, and the alternative typology
engine `ollama_typology` when you select it instead of the default `deberta_typology`. The rest of
the pipeline — transfer, cleaning, NER, typology on the default engine, thumbnail, macro-category,
embedding — runs without Ollama.

Start the host and pull the tags the panel lists as missing; `OLLAMA_HOST_URL` is what reaches the
engines, and an explicit `--option host=...` still overrides it for a single run.

One preset was retired instead of fixed: `granite_local` named `granite4.1:3b`, which on Ollama
0.24.0 terminates the llama runner with `signal arrived during cgo execution` and answers `500` to
every prompt, while `gemma4:e4b` answers normally on the same server (measured 2026-10-18). The name
is no longer offered and the health probe no longer requires the model. A settings row or an
`LLM_CHECK` rule that still names it is refused when written, and one written before the retirement
resolves to `gemma_4b_local` with the reason on the screen instead of taking the panel down.

### The bucket does not answer

The panel distinguishes the two cases: `storage.configured = false` means endpoint, bucket or
credentials are missing, and `configured = true, ok = false` means the configuration is there and
`HEAD` on the bucket failed. The `thumbnail` worker is the only consumer of the bucket, so the rest
of the pipeline continues. Bring the bucket up **before** running that worker: a document whose
upload raises is stamped `thumbnail_failed`, a permanent-failure mark the queue honours, so a
transient storage outage during a run leaves those documents excluded from every later run. Correct
`S3_ENDPOINT_URL`/`S3_BUCKET_NAME`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`, confirm the bucket exists, and
check reachability from the process doing the upload — inside a container, `localhost` is the
container.

## Next steps

- [Operations](operate.md) — the nine workers and their order, presets and overrides, the run ledger
  and how to reprocess a document or a batch.
- [Curation](curate.md) — what the archivist decides on each screen, and which writes have no undo.
- [Data model](data-model.md) — the three layers plus `identity`, the stamps and the ledgers.
