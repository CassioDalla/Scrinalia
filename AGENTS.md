# Scrinalia — Constitution

Scrinalia is a system for archivists: it catalogs and manages archival descriptions (ISAD(G) metadata)
with AI enrichment (NER, zero-shot classification, clustering) and Human-in-the-Loop governance. Three
layers, each a domain under `src/scrinalia/domains/` — `ingestion` (scraping queue) -> `staging`
(structured, cleaned data) -> `archive` (final enriched document + human review). A fourth domain,
`identity`, is not a layer of that pipeline: it owns the accounts, the sessions and the role map
(ADR 0009).

This file is the **constitution**: the general, stable rules that bind every change. It is not the whole
manual. The detail that enforces each principle lives in a **rule file** — a skill under
`.dsh/skills/` — named in the index at the end; open the rule file for the topic you are touching
*before* you touch it. A rule file states what this file only names, and this file states what a rule
file never repeats.

## Core Principles

### I. Measured, not assumed (NON-NEGOTIABLE)

A statement about this system MUST be something you verified in this checkout, and a green gate is not
verification. `tsc`, ESLint and the Vite build were all green while 105 bracket-form Tailwind tokens
rendered nothing; only looking at the page found it. Give evidence with its number ("52.9 s with the
OR, 1.4 s without, identical results") and name what you did **not** verify — `docs/log.md` has the
form: *"not looked at in a browser; the evidence is `tsc`, ESLint, the Vite build"*. Never describe a
screen, a query plan or a behaviour you did not observe.

**Rationale:** a confidently wrong statement is more expensive than a declared gap, and every rule file
below exists because a plausible assumption was measured and found false.

### II. The code is English; the user's text is Portuguese (NON-NEGOTIABLE)

Filenames, identifiers, comments, docstrings, log messages, internal errors, ADRs, commits and these
files are English. Portuguese appears only where a person reads it: the curator SPA's strings, an API
response `message`, and a `DomainException` the API forwards. Never translate a source literal that must
match an external payload or an LLM prompt written to reason about Portuguese text. `ValueError` is not
a client error — use a `DomainException` when the API owes a business status.

**Rationale:** an institution installs this system in its own language, so end-user text has to be
translatable and everything else has to be readable by whoever joins the code next.

### III. The API is the contract (NON-NEGOTIABLE)

`packages/api-contract/openapi.json` and `apps/curator/src/api/schema.d.ts` are generated and committed,
and CI fails when either is stale. The front reaches the API only through `apps/curator/src/api/client.ts`
(openapi-fetch) — a hand-built URL or the `fetch` global is an ESLint error — and it never queries
Postgres.

**Rationale:** the SPA is one consumer of a contract that a second surface (the public site) will share.
A stale copy of a contract is a bug that compiles.

### IV. One definition per concept

Where two places can disagree, one MUST be removed or derived: a worker is defined once
(`workers/catalogue.py`), a merge is planned once (`plan_merge`), a failure's root cause is one generated
column fed by one SQL function, an engine's read-only twin describes exactly what the engine receives,
and a facet filters by the expression it groups by. A second implementation is a defect, and a test MUST
pin the pair that cannot be merged.

**Rationale:** every duplicated definition in this project's history drifted, and the drift was always
discovered by a user rather than by a gate.

### V. What matters becomes a gate

A convention that can be checked MUST be a test that fails: an unclassified route, an undocumented
catalogue item, a non-deterministic contract, a message without a code, a trigram join that lost its
index. The gate makes a mistake impossible by accident and possible only deliberately, in a diff a
reviewer reads. This file obeys the same rule: its size and its rule-file index are checked by
`testing/unit/docs/test_agents_constitution.py`.

**Rationale:** the repository's own history is the argument — the defects that hurt were the ones no gate
covered, and each of them became a test the day it was found.

### VI. The decision, the write and the read are separate

A plan or a preview MUST be computable without writing (`/preview`, `--dry-run`, `suggest`); a write MUST
leave a ledger that makes it reversible; and a catalogue row retires (`is_active=false`) instead of being
deleted, because its FK is `SET NULL` and deleting would erase the record that it ever existed. What has
no undo MUST be gated by a preview that lists what would die. A human verdict is durable intent that a
later suggestion run never overwrites.

**Rationale:** an archivist's work is a series of decisions about a collection that cannot be
reconstructed from memory, so the system has to be able to show *why* a row changed and to put it back.

### VII. A human decision outranks the AI (NON-NEGOTIABLE)

`HUMAN_APPROVED` blocks every AI rewrite (`ai_writable_documents()`). The one documented exception —
`worker_embedding` re-embeds a changed text even on an approved document, because the vector is a derived
index and not archival content — MUST stay documented where it is. Governance is bidirectional and its
two directions are stored apart on purpose (a tag-scoped stopword versus an entity exclusion); do not
collapse them.

**Rationale:** the model proposes and the archivist decides; a system that lets the second overwrite the
first is not a cataloguing tool, and the cost of the wrong default is silent.

### VIII. Work lands in `dev` through a reviewed, signed commit

One commit is one logical change, in Conventional Commits, and every commit carries the DCO sign-off
(`git commit -s`). A change goes on its own branch and lands in `dev` through a pull request; `main`
moves only at a release, through the manual Release workflow. The checks `CONTRIBUTING.md` lists are run
locally before the PR, and the pre-commit hooks are not skipped.

**Rationale:** the history is the only place the reasoning survives, so it has to be reviewable one
change at a time and attributable.

## Layout and entry points

- Layout: `src/scrinalia/` is the installed namespace (`api/`, `core/`, `domains/`). `main.py` at the
  root only re-exports `scrinalia.asgi.app` so `uvicorn main:app` keeps working; put application code in
  the package, never in `main.py`. `testing/`, `migrations/` and `docs/` live **outside** the package on
  purpose. There is no `scripts/`: one-off tooling is deleted once it has served its purpose instead of
  being kept at the root, where it rots with stale imports. See
  `docs/adr/0002-src-layout-and-internal-namespace.md`.
- API: Litestar, assembled in `src/scrinalia/asgi.py` (`create_app()`), NOT FastAPI. Decision recorded
  in `docs/adr/0001-litestar-as-http-framework.md`.
- Front: the curator UI is the React SPA in `apps/curator/` (ADR 0003). It is the only front end: the
  temporary Streamlit dashboard was removed in B8. Treat the API as the stable interface.

### Commands

Always run from the repo root. Python 3.12, managed by `uv` (`uv.lock`).

- Install: `uv sync` (heavy: `torch`, `transformers`, `spacy`, `bertopic`). Whole dev stack:
  `bun run dev` — `docker compose up -d`, then the API on `:8000` and the SPA on `:5173`. The pieces run
  alone too: `bun run db:up`, `bun run api:dev`, `bun run curator:dev`. **A 502 on `/api` from the Vite
  dev server means the API is not up** (the proxy targets `localhost:8000`); the SPA itself still answers
  200, which is what makes the symptom look like a front-end bug.
- API: `uv run uvicorn main:app --reload`.
- Curator UI: `bun install` once at the repo root, then `bun run curator:dev` or `bun run curator:build`.
  **Bun manages packages and scripts; Vite is the bundler** — do not replace it with `bun build`
  (ADR 0003). `bun run --cwd apps/curator typecheck|lint`.
- Contract: `bun run contract` regenerates `openapi.json` and the TypeScript client (principle III).
- Migrations: `uv run alembic upgrade head`; `uv run alembic check` must report no drift.
- Workers: `uv run python -m scrinalia.domains.archive.workers.runner <name> [--engine X --preset Y
  --batch N --option k=v --by "quem"]`; the names, the pipeline order and the panel are the rule file
  `workers`.
- Tests: `uv run pytest` from the root; one test is
  `uv run pytest testing/unit/archive/workers/test_worker_ner.py::test_name`. The fixtures and the test
  database are the rule file `testing`.
- Lint/format: `uv run ruff check .` and `uv run ruff format .` (line-length 120, double quotes). CI
  enforces `ruff format --check .`.
- Types: `uv run basedpyright`, whose scope lives in **`pyrightconfig.json`** and not in a `[tool.*]`
  section — Pylance ignores `[tool.basedpyright]`, and a `[tool.pyright]` section makes basedpyright
  ignore its own section and drop to its defaults (measured: 661 errors). Do not move it into
  `pyproject.toml`.
- Hooks: `uv run pre-commit install` once per clone; `uv run pre-commit run --all-files` by hand.
- Deploy: `Procfile` runs the API on the CPU; `create_app()` mounts `apps/curator/dist` at `/` when the
  build exists, so a deploy builds the SPA first (rule file `api`).

## Documentation and language

- `README.md` is the front door for newcomers (what the system is, how to run it); the work that is left
  lives in the GitHub issues and their milestones, the accepted architecture decisions in `docs/adr/`,
  and the guides an installer, an operator and an archivist read in `docs/guides/`. Keep them in step
  with the code, and never state something in them that you have not verified.
- **The documentation is versioned with the code and held to it by two rules (ADR 0010).**
  *Coverage is a gate*: `testing/unit/docs/test_documentation_coverage.py` walks the real catalogues and
  fails when a worker, a settings field, a screen, a table or an ADR is missing from the page that owns
  it — the documentation twin of `test_route_access.py`, so an item cannot go undocumented by accident,
  only deliberately in a diff. *Freshness is a report*: each guide declares the code it documents in its
  front matter (`sources:`), `uv run python docs/_hooks/freshness.py` prints what moved since the last
  commit that touched the page (plus the route delta when the contract moved), and `docs/log.md` records
  the verdict — `updated`, or `no-change` with a reason. **A page never stores a revision and never
  stores a `reviewed:` field**: the marker is derived from git, because a page cannot name the commit
  that contains it. The `documenter` skill is the procedure for a triage round.
- **English is canonical in the documentation; Portuguese is a translation of it.** `page.md` +
  `page.pt.md` (`mkdocs-static-i18n`, suffix structure, falling back to the English page when a
  translation is missing). Write the English page first and translate it — never let the translation be
  the only place a fact lives. The ADRs are English-only on purpose: they are the reasoning of the code,
  not operator text. `uv sync --group docs`, then `uv run mkdocs serve`; CI builds the site with
  `--strict`, so a broken link fails like a broken import.

## License

- **`AGPL-3.0-only` plus one additional term** under section 7(b) requiring the author attribution to be
  preserved (`LICENSE`, `LICENSE-ADDITIONAL-TERMS.md`, ADR 0006). Two rules: never inline the attribution
  text in a component — it is defined once in `apps/curator/src/lib/attribution.ts` and rendered by
  `AttributionFooter` through `AppShell`, so every screen shows it and a rename touches one line; and
  never add a term beyond attribution, because the license declares any other non-permissive additional
  term to be a "further restriction" that section 10 forbids imposing. "Modifications must be
  contributed back" is a request in the `README`, not a condition — no license can require it.

## Governance

- **Authority.** The principles bind every change. Where a rule file and this file disagree, this file
  wins and the rule file is fixed in the same change.
- **Amendments.** Changing this file is a pull request with a rationale and a version bump: MAJOR removes
  or redefines a principle, MINOR adds a principle or a rule file, PATCH clarifies. The amendment
  propagates in the same change — the index below, the rule file it touches, and an ADR when a recorded
  decision changed.
- **Sync is a gate.** Every rule file cited below MUST exist, and every existing rule file MUST be cited.
  The footer MUST read `**Version**: x.y.z | **Ratified**: <date> | **Last Amended**: <date>`. This file
  MUST stay inside the byte budget held in `testing/unit/docs/test_agents_constitution.py`; the budget
  ratchets **down**, and raising it is an amendment with its reason in the PR.
- **Compliance.** Every PR verifies the principles; a violation is fixed by changing the code or the
  spec, never by diluting a principle. Added complexity is justified in the PR.

## Rule files

A skill per topic. Open the one that owns what you are about to touch.

- `api` — the package's conventions and the HTTP surface: DDD layout, Litestar handler annotations,
  repositories, the ISAD(G) curation commands, response codes and the generated contract.
- `workers` — engines and workers: registry, idempotency stamps, the AI text composition,
  HUMAN_APPROVED governance, the run ledger, presets and the operations panel.
- `taxonomy` — the subject axis: plan/apply merges, the proposal lifecycle, ledgers and their undo,
  scoped stopwords and exclusions, conflicts, and the catalogues that retire.
- `hierarchy` — arrangement: levels, plans, flags, diagnostics and the `path` invariant.
- `search` — search and diffusion: lexical vs semantic, the synonyms match, facets, the public surface,
  trigram joins, LIKE escaping and the type-aheads.
- `curator-ui` — the SPA: Tailwind v4 tokens, the generated client as the only seam, the permission
  mirror.
- `ingestion` — the origin and the language: `SourceSchema` labels, no default origin, the false-null
  vocabulary, the staging -> archive key and the language profile.
- `data` — schema, migrations, settings and logging.
- `testing` — the suite, its fixtures and the Postgres test database.
- `observability` — health probes, the failure ledgers, the error fingerprint and request correlation.
- `auth` — access classification, the guard, sessions, lockout, rate limiting and the ADMIN surface.
- `render` — whether this machine can render a screen and how; and what to say when it cannot.
- `commit` — the commit format and the DCO sign-off.
- `documenter` — the procedure for a documentation triage round.

**Version**: 1.0.0 | **Ratified**: 2026-10-09 | **Last Amended**: 2026-10-09
