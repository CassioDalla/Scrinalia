# Scrinalia

A system for archivists to catalogue and manage archival descriptions (ISAD(G) metadata),
with AI-driven enrichment and Human-in-the-Loop governance.

The system ingests descriptions from a public archival source, normalises them through a
three-layer pipeline, and enriches them with named entities, typologies and subject
categories. Every AI decision is advisory: an archivist reviews and approves, and approved
documents are locked against further automatic rewrites.

> **Status:** research project under active development. The curator UI is a React SPA
> (`apps/curator/`) served by the API. The HTTP API is the stable contract, and the TypeScript
> client is generated from it. The public diffusion site (`apps/public/`) is planned; the public
> projection and its routes already exist on the API.

## How it works

Three layers, each one a domain under `src/scrinalia/domains/`:

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

The subject axis reads a **vocabulary**, not the raw tag list: eight drawers derived from the
collection, plus two kinds of "this is not a subject". The split follows the owner of each piece.
What is a property of **Portuguese** — `rua`, `não identificado`, a bare year, `303 anos` — lives in
a language profile (`core/language`, selected by `ACERVO_LANGUAGE`): it is not a curation decision,
and a second language is a module rather than a second parser. What is a property of **this
collection** — the bairros it names, the people it depicts, the tokens its reference codes carry —
is a catalogue the archivist edits at `/vocabulario` (`archive_collection_terms` and
`archive_arrangement_vocabulary`), seeded with the reference collection and replaceable without a
deploy. On top of the deterministic guard sits the curated `domain_subject_exclusions` catalogue,
for the judgements no rule reaches. Below 0.55 confidence a tag is left without a drawer **and**
queued for review rather than guessed at. A tag whose axis is provenance or geography (`ippuc`,
`curitiba`) carries an `archive_tag_facets` row instead of competing for a subject drawer.

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

# 5. Create the first administrator (prints a temporary password, to be changed at first sign-in)
uv run python -m scrinalia.domains.identity.cli create \
  --email voce@instituicao.org --name "Seu Nome" --role ADMIN

# 6. Run the API
uv run uvicorn main:app --reload
```

The API is then available at `http://localhost:8000/`, with the OpenAPI schema at
`/schema/swagger`.

### Running the whole system in a container

The image contains the API **and** the curator SPA. That is the deployment shape the code already
assumes rather than a packaging choice: `create_app()` mounts `apps/curator/dist` at `/` when the
build exists, so the SPA has no process of its own, the browser stays on the same origin as the API
and the project needs no CORS — which is also what makes the session cookie first-party and what
`origin_guard` compares against. A second container in front of the API would have to re-create that
same origin and a CORS configuration the project deliberately does not have.

```bash
docker compose --profile app up -d --build   # application + PostgreSQL + MinIO
# → http://localhost:8000
```

PostgreSQL, MinIO and Ollama stay outside the image; only `DB_HOST`, `S3_ENDPOINT_URL` and
`OLLAMA_HOST_URL` change to reach them. The service sits behind the `app` profile, so
`docker compose up -d` — and therefore `bun run dev` — keeps starting the infrastructure alone.
Port 8000 is the one `bun run api:dev` uses; do not run both at once.

The entrypoint applies `alembic upgrade head` before starting `uvicorn`, retrying while the database
is still coming up (`SCRINALIA_DB_WAIT_SECONDS`, default 60) and giving up with a non-zero exit when
it is genuinely unreachable. Set `SCRINALIA_RUN_MIGRATIONS=false` to skip it when migrations are a
separate step. The first administrator is created from inside the container:

```bash
docker compose --profile app exec app \
  python -m scrinalia.domains.identity.cli create \
  --email voce@instituicao.org --name "Seu Nome" --role ADMIN
```

Two properties of the image are load-bearing before changing it. It runs **one** API process on
purpose: the worker executor lives inside the API and `api/lifespan.py` marks any `QUEUED`/`RUNNING`
run it finds at start-up as `INTERRUPTED`, so `--workers > 1` requires moving the executor out first.
And the Python environment is installed **editable** at `/app/src`, which is what `api/spa.py`'s
`parents[3]` needs to find the SPA build — `--no-editable` deploys an API with no UI, silently.

> The lockfile pins the PyPI `torch`, whose Linux wheel pulls the whole CUDA runtime into the image
> even though the container runs on CPU (`CUDA_VISIBLE_DEVICES=""`, as in the `Procfile`). A CPU-only
> image needs a different resolution of the PyTorch stack, which belongs in `pyproject.toml`/`uv.lock`
> — so that CI and the image keep building the same dependency graph — and not in the Dockerfile.

`GET /health/live` and `GET /health/ready` are the orchestrator's probes, and they sit outside
`/api/v1` and outside the schema on purpose. Liveness touches nothing and answers 200 while the
process answers; readiness runs `SELECT 1` and answers **503** when the database does not, so a
database restart takes the instance out of rotation without restarting the process. The human
diagnosis is a different question and a different route: `GET /api/v1/system/health` reports *which*
piece is down — database, Ollama models, bucket, effective process configuration — and answers 200
either way.

### Authentication

Every operation of `/api/v1` requires a session, and the **only** things reachable without one are the
login, the diffusion routes (`/api/v1/public/*`), the health probes and the OpenAPI document. The
decision and its alternatives are in [ADR 0009](docs/adr/0009-authentication-and-authorization.md).

Accounts live in the database (`auth_users`), passwords are hashed with **argon2id**, and the session
is a first-party cookie whose row lives in `auth_sessions` — only the SHA-256 of the token is stored,
which is what makes "sign out everywhere" and "this person no longer works here" take effect at once
instead of at expiry.

An `ADMIN` manages the accounts from the curator UI, under **Configurações › Usuários**: create,
change a role, deactivate, reset a password, and see or end the active sessions of any account. A
password created there is temporary — the account replaces it at the first sign-in — and deactivating
an account ends its sessions immediately. The **last active administrator** cannot be deactivated or
demoted, so the installation can never lock itself out of the UI.

The host CLI remains for the bootstrap and for the way back in:

```bash
uv run python -m scrinalia.domains.identity.cli list
uv run python -m scrinalia.domains.identity.cli create --email a@b.org --name "Ana" --role CURATOR
uv run python -m scrinalia.domains.identity.cli reset-password --email a@b.org
uv run python -m scrinalia.domains.identity.cli deactivate --email a@b.org
```

Three roles: `ADMIN` (accounts and the AI workers), `CURATOR` (the record, its subjects and the closed
catalogues) and `VIEWER` (reads). There is no self-service password recovery by e-mail — the CLI on the
host is the way back in, which is deliberate for an installation with no mail server.

**Repeated failed sign-ins lock the account**, and the window doubles with each further lockout up to a
ceiling (`AUTH_LOGIN_MAX_ATTEMPTS`, `AUTH_LOGIN_LOCKOUT_MINUTES`, `AUTH_LOGIN_LOCKOUT_MAX_MINUTES`).
The count is a column, so it survives a restart; resetting the password lifts the lock, and the accounts
screen shows a locked account and how many attempts it has. In front of it there is a per-address brake
on the login route (`AUTH_LOGIN_RATE_MAX` per `AUTH_LOGIN_RATE_WINDOW_SECONDS`, answering 429) which
lives in the process and resets with it — the durable defence is the lockout.

Mutating requests are also checked against their `Origin`: same-origin is accepted, and a deployment
behind a reverse proxy that rewrites `Host` declares the public origin in `AUTH_TRUSTED_ORIGINS`. A
request with no `Origin` (curl, the CLI) is accepted, and reads are never checked.

**One setting to change before exposing the instance:** `AUTH_COOKIE_SECURE=true` behind HTTPS. Left
false over the open internet, the session token travels in clear text.

### Curator UI

The archivist's interface is a React SPA in `apps/curator/`. It has no server of its own: Vite
proxies `/api` to the API in development, and in production the API serves the built files, so the
browser is always on the same origin and the project needs no CORS configuration.

```bash
bun install                                   # once per clone, from the repository root
bun run dev                                   # infra + API (:8000) + SPA (:5173) in one command
bun run curator:build                         # writes apps/curator/dist, served by the API at /
```

`bun run dev` is the whole development stack: it brings the containers up (`docker compose up -d`),
starts the API and starts the SPA. Run the pieces separately when you only want one of them:

```bash
bun run db:up      # docker compose up -d — PostgreSQL and MinIO
bun run api:dev    # uv run uvicorn main:app --reload — the API alone, on :8000
bun run curator:dev  # the SPA alone, on :5173
```

> **A 502 on `/api` means the API is not running**, not that the front is broken: Vite proxies `/api`
> to `localhost:8000`, so the SPA still loads (200) while every request fails. `bun run curator:dev`
> starts only the front — use `bun run dev`, or start `bun run api:dev` in another terminal. If Vite
> prints a different port, `:5173` was already taken and the URL is the one it prints.

The TypeScript client is **generated from the API contract**, never written by hand:

```bash
bun run contract          # dumps packages/api-contract/openapi.json and regenerates the client
```

CI fails when either artifact is stale, so a route or a schema change that is not accompanied by a
regenerated contract is caught at review time rather than in the browser.

The screens that exist today, in the order the work happens:

| Route | What it is for |
| --- | --- |
| `/` | the work list: what needs the archivist today, one card per queue |
| `/acervo/lista` | search and facets over the collection (lexical or semantic) |
| `/acervo/arvore` | the arrangement as navigation: roots, branches and the descriptions inside them |
| `/acervo/:id` | the dossier: description, subjects, arrangement and history |
| `/acervo/excluidas` | the trail of the deleted descriptions: a snapshot of each, and no restore |
| `/arranjo/plano` | the arrangement plan: decide the proposed levels, preview and materialise |
| `/arranjo/diagnostico` | the structural diagnosis, one section per problem, with the evidence |
| `/arranjo/niveis` | the NOBRADE ladder: weight per rung, editable, never deleted |
| `/arranjo/tipologias` | the documental typologies the classifier proposes: active ones are the labels, retired ones keep their weight |
| `/assuntos/tags` | the tag catalog: weight, near-duplicates and the merge queue with undo |
| `/assuntos/categorias` | the subject drawers the classifier reads, with their weight |
| `/assuntos/descobrir` | cluster the vocabulary to discover a drawer it does not have |
| `/assuntos/excecoes` | "this is not a subject at all": the terms the deterministic guard already refuses, with the evidence, plus the field for the judgements no rule reaches |
| `/entidades/lista` | named entities: weight by type, merge and reclassification |
| `/entidades/excecoes` | the NER veto: "this spelling is a subject, not a proper name" |
| `/entidades/conflitos` | the tag x entity collision in three reads — pending (filtered by population), what the judge decided, and the ledger with its undo — with the impact of both verdicts shown before the click |
| `/qualidade/trechos` | repeated excerpts, the scope that drops them and the mandatory dry run |
| `/qualidade/regras` | cleaning rules: `REWRITE` replaces, `VALIDATE`/`LLM_CHECK` only flag |
| `/qualidade/anomalias` | what the quality validator marked, with the reason counts over the whole filtered set and each reason as the filter |
| `/sistema/workers` | the AI workers: engine, preset and model, the queue, the persisted default and a run button |
| `/sistema/execucoes` | the execution ledger, and the failures of the last 30 days grouped by root cause; clicking a cause filters the ledger to its occurrences |
| `/sistema/diagnostico` | database, Ollama models, thumbnail storage and the effective process configuration |

The arrangement screens offer no silent correction: every write is a decision taken on a screen
that showed its impact first, and the applied materialisations are reversible from the ledger.
Where a write has no undo — the stopword purge, an entity merge, and the deletion of a description —
the screen says so before the click instead of after it. The deletion is the only write that removes a
record: it refuses a node that still has children, asks for the reference code to be typed, and leaves
the whole ISAD(G) snapshot in `archive_document_deletions`, which is a trail and not a recycle bin.

## Running the workers

Prefer the unified runner, which exposes every worker behind one interface:

```bash
uv run python -m scrinalia.domains.archive.workers.runner <name> \
    [--engine X --preset Y --batch N --option key=value --by "who"]
```

Available names: `transfer`, `cleaning`, `ner`, `typology`, `thumbnail`, `conflict-judge`,
`macro-category`, `quality-validator`, `embedding`.
Each `worker_*.py` also carries an `execute(db, ...)` function and a `__main__` block, so a
single worker can be run directly while developing.

A worker runs with the **effective configuration**, which is `explicit argument > persisted
override > signature default`; `/sistema/workers` in the curator UI shows it, changes it and runs
the worker, and every run — from the CLI or from the screen — leaves a row in
`archive_worker_runs` with the resolved configuration, the duration and the outcome. The screen's
executor runs one worker at a time and is not a scheduler: there is no retry and no cron
(`docs/adr/0004-worker-execution-from-the-api.md`).

## Development

```bash
uv run pytest                 # full suite
uv run pytest -m unit         # fast tests, no database needed
uv run ruff check .           # lint
uv run ruff format .          # format
uv run basedpyright           # type check
uv run pre-commit install     # once per clone
```

> **When the checkout cannot write to `~/.cache`** — a sandboxed agent, a container with a read-only
> home — export both caches into the workspace, which is already gitignored, and run the hooks with
> the venv binary so `uv`'s own cache is not needed either:
>
> ```bash
> export PRE_COMMIT_HOME=.cache-pre-commit
> export UV_CACHE_DIR=.cache-uv
> .venv/bin/pre-commit run --all-files
> ```
>
> The same variables are what makes `git commit` work: the installed hook calls `.venv/bin/python3`
> directly, but pre-commit still stashes the unstaged files into `PRE_COMMIT_HOME` and fails with
> `Read-only file system` when that directory is `~/.cache/pre-commit`. The cache stores absolute
> paths, so after the checkout directory is renamed it has to be rebuilt (delete `.cache-pre-commit`
> and run the command above). The three hooks are the same three checks CI runs: `ruff`,
> `ruff format` and `basedpyright`.

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
src/scrinalia/   the application (installed package)
  api/                    Litestar controllers, request schemas, composition root
  core/                   settings, logging, database, unit of work
  domains/                ingestion, staging, archive (models/repository/services/workers)
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
- [`docs/adr/`](docs/adr/) — architecture decision records, including
  [`0006`](docs/adr/0006-license-and-author-attribution.md) on licensing,
  [`0007`](docs/adr/0007-project-name-scrinalia.md) on the name,
  [`0008`](docs/adr/0008-language-in-code-and-collection-vocabulary-in-the-database.md) on what is
  language, what is collection data and what is configuration, and
  [`0009`](docs/adr/0009-authentication-and-authorization.md) on authentication and authorization

## Contributing and security

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to set the project up, what a pull request has to pass,
  the commit conventions, and the **DCO** (sign your commits with `git commit -s`).
- [`SECURITY.md`](SECURITY.md) — **report a vulnerability privately**, through the repository's
  Security tab. Never in a public issue.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) and [`CHANGELOG.md`](CHANGELOG.md).
- If you use Scrinalia in academic work, [`CITATION.cff`](CITATION.cff) has the citation.

## The name

**Scrinalia** is coined from the Latin `scrinium`, the case that held scrolls — and, by extension,
the record offices of the later Roman and Byzantine administration (`scrinium memoriae`,
`scrinium epistularum`, `scrinium libellorum`), whose officials, the *scriniarii*, were archivists.
Portuguese keeps the root in *escrínio*, a cabinet for papers.

The `-alia` ending is the Latin neuter plural that gives *marginalia* and *memorabilia*, so the name
reads as **"the things of the archive"** — a plural collective, which is what the system holds: a
body of descriptions, kept together and made findable.

It is not a dictionary word, and that is the point. Every real archival term tested was already in
use somewhere that mattered — a government records system, a registered trademark, a live product —
so the name takes a real root in a regular form that happens to be unclaimed: free on every package
registry, on every domain tested, and as a username. It has exactly one spelling. The reasoning, the
candidates that were rejected and the evidence against each are in
[ADR 0007](docs/adr/0007-project-name-scrinalia.md).

## License and attribution

**AGPL-3.0-only**, plus one additional term added under section 7(b) of that license requiring the
author attribution to be preserved. [`LICENSE`](LICENSE) is the verbatim license text;
[`LICENSE-ADDITIONAL-TERMS.md`](LICENSE-ADDITIONAL-TERMS.md) states the term; and
[`docs/adr/0006`](docs/adr/0006-license-and-author-attribution.md) records the decision and the
alternatives that were rejected.

What that means in practice:

- **Use it, study it, modify it, redistribute it, run it as a service.** Installing this for your
  own archive obliges you to nothing at all, and no public body has to ask permission.
- **You may charge for it.** The license says so explicitly (§4). What you may not do is take it
  closed: if you modify it and let users reach it over a network, section 13 requires you to offer
  those users the Corresponding Source of your version.
- **Keep the attribution.** The footer carries the author, the license, a link to the license text
  and a link to this repository. It has to stay there, and a modified version has to keep all four.
  This is the only condition the project adds beyond the license itself.
- **Changes should come back — but no license can require that.** Section 13 obliges offering
  source to the users of your deployment, not filing a pull request here. If you fix something for
  your archive, opening a pull request is how this project improves, and it is very welcome; it is
  a request, not a condition.

Never write the attribution text by hand in a component. It is defined once, in
[`apps/curator/src/lib/attribution.ts`](apps/curator/src/lib/attribution.ts), and rendered by
`AttributionFooter` through the application shell — so a rename changes one line, not every screen.
