# ADR 0010: Documentation versioned with the code, gated by coverage and tracked by a freshness ledger

- **Status:** Accepted
- **Date:** 2026-10-08

## Context

Phase 5 of `TODO.md` had one blocker left: a documentation base. What existed: nine ADRs under
`docs/adr/`, `README.md` as the front door, `TODO.md` as the roadmap and `AGENTS.md` as the set of
rules that are easy to get wrong. What did not exist: a guide for installing and deploying, a guide
for operating the workers, a guide for curating, a data-model reference, any index over the ADRs,
and — the part this ADR is really about — **any way to tell whether a page still describes the
code**.

The facts that shaped the decision:

- **The system is installed by another institution, offline.** The same reasoning as ADR 0005: a
  documentation site that depends on an account somebody else owns is worth nothing to an
  installation that runs on-premises. The documentation is versioned in the repository and built
  from it.
- **The audience is split, and the project already draws the line.** The archivist reads Portuguese
  (the SPA is Portuguese), the operator and the contributing institution read English. The
  language rule in `AGENTS.md` — code in English, end-user-visible text in Portuguese — applies to
  the documentation unchanged: **English is canonical, Portuguese is a translation of it**.
- **The repository already knows how to stop a generated artifact from silently drifting.**
  `packages/api-contract/openapi.json` is generated, committed, and CI fails when it is stale;
  `alembic check` fails on schema drift; `testing/unit/api/test_route_access.py` fails when a route
  ships without a declared permission. Documentation had no equivalent, and the reflex it protects
  against is the normal one: the code moves, the page does not, and nothing says so.
- **The surfaces that can be enumerated are known and small**: 9 workers in
  `workers/catalogue.py`, 32 settings fields in `core/config.py`, 24 screens in
  `apps/curator/src/router.tsx`, the 34 tables of `Base.metadata`, the ADRs on disk, and the 95 paths /
  112 operations of the committed contract. The counts are measured, not estimated: the coverage
  test recomputes every one of them from the code.

The choice that shaped everything else: whether a page's freshness is **declared** by whoever edits
it (a `reviewed: <sha>` field) or **derived** from git.

## Decision

1. **MkDocs Material, sources in `docs/`, config in `mkdocs.yml`.** The site is built in CI with
   `--strict`, so a broken link or a malformed block fails the same way a broken import does. There
   is no hosted deployment yet; publishing is a later decision, and `mike` (per-release versioning)
   is deliberately not adopted until there is a site to version.
   **Amended by [ADR 0012](0012-the-documentation-site-is-published-by-ci.md):** there is a hosted
   deployment now — the site is published from CI into the Pages artifact on a push to `main` — and
   `mike` is still not adopted, for the sharper reason that ADR records.
2. **English is canonical; Portuguese is a translation.** A page and its translation sit side by
   side as `page.md` and `page.pt.md` (`mkdocs-static-i18n`, suffix structure, fallback to the
   default), so an absent translation serves the English page instead of answering 404. The index
   and the four guides are translated; **the ADRs are not** — they are the reasoning of the code,
   a historical record, not operator-facing text.
3. **Divergence has two axes, and they are treated differently.**
   - **Coverage is decidable and blocks.** `testing/unit/docs/test_documentation_coverage.py` walks
     the real catalogues and fails listing what a page forgot: every worker of the catalogue
     appears in the operations guide, every settings field in the install guide, every screen in
     the curation guide, every table in the data model, every ADR in the index. It is the
     documentation twin of `test_route_access.py`: a new worker cannot ship undocumented by
     accident, only deliberately, in a diff.
   - **Freshness is a judgement and only reports.** Each page declares, in its front matter, the
     code it documents (`sources:`). A page is a *stale candidate* when git says one of those
     sources changed after the last commit that touched the page. A translation declares
     `translation_of:` and is a stale candidate when the page it translates changed after the last
     commit that touched the translation.
4. **No page stores a revision, and there is no `reviewed:` field.** The marker is derived from
   git, for two reasons. A page cannot honestly name the commit that contains it — the sha does not
   exist while the page is being written — and a stored sha has to be re-written by every triage,
   which is bookkeeping that rots the first time somebody bumps it without reading the diff.
   `sources:` and `translation_of:` are declarations an author can make truthfully at writing time.
5. **The judgement is recorded where judgements live in this repository: in a ledger.**
   `docs/log.md` carries one entry per triage round — the commit range triaged, the date, and, per
   page, `updated` or `no-change` with one line of reason. A page that is stale and correct is
   explicitly closed, so the same range is not re-litigated next round and a reviewer can see why
   a stale page was left alone.
6. **The freshness report is served by one MkDocs hook** (`docs/_hooks/freshness.py`). It reads the
   front matter and git, prints a per-page report, and adds a route-level delta when
   `packages/api-contract/openapi.json` is inside the range — "what changed in the surface" is a
   far better signal than "these twelve commits landed". It runs on every build, so CI prints it
   for free, and it is runnable alone (`uv run python docs/_hooks/freshness.py`).
7. **The checker lives in `docs/_hooks/`**, not in the package and not in a `scripts/` directory:
   `docs/` is deliberately outside the installed namespace (ADR 0002), the hook is a supported
   MkDocs extension point, and `scripts/` does not exist on purpose.

## Rationale

- **The documentation is only trustworthy if a stale page is visible, and only maintainable if
  staleness is not a build break.** Blocking on freshness would be a build that fails on a
  judgement, and the cheap way out of such a build is to bump the marker without reading the
  change — the exact behaviour that makes the tracking worthless. Coverage is different: it is a
  fact, and a fact belongs in a gate.
- **Deriving the marker from git is what makes the ledger honest.** `sources:` says what the page
  is about; git says what happened to it since. Neither needs to be maintained by hand, and
  neither can claim on the page's behalf that somebody looked at it. Only the ledger makes that
  claim, and it carries a name and a reason because that is the part a human owes.
- **The four guides follow the four decisions the TODO already separated**: what an installer
  needs, what an operator does, what an archivist decides, and what the data means. That
  separation is not editorial — it is the same separation the code makes between deployment
  (`Dockerfile`, `Procfile`, `AUTH_*`), operation (`workers/catalogue.py`, the run ledger), human
  decision (the screens and their reversibility) and the schema (three layers plus `identity`).
- **Portuguese is a translation of the English page, not a second source.** The alternative —
  two hand-maintained trees — makes the two disagree silently, and then the disagreeing language
  is the one the archivist reads. Translating the ADRs is not a translation problem but an
  editorial one: an ADR records what was decided and why at a point in time, and a translated ADR
  is a second record of the same decision.
- **`mkdocstrings` is not adopted.** It would publish internal docstrings, which are not a curated
  surface: they document the code for whoever is reading the code, and putting them on the site
  creates a second documentation surface with no owner. The API already has a single, generated,
  CI-gated definition in `packages/api-contract/openapi.json`.
- **Coverage is checked against the committed contract, not against a running application.** The
  test reads `openapi.json` and imports the worker catalogue, which is deliberately cheap (it
  imports no worker). A documentation gate that needs a database is a gate that gets skipped.

## Consequences

Positive: a new worker, setting, screen or table cannot reach `main` without a page mentioning it,
and the failure names the missing item; a page whose subject moved is reported with the change that
moved it, in every build; the decision not to update a page is a dated line with a reason, which is
what makes "the docs are current" an auditable claim instead of a feeling; and an institution that
installs the system can read the guide in Portuguese while the repository keeps one canonical
English text.

Negative, and accepted:

- **Freshness is reported, not enforced.** A contributor can merge a change whose page is now
  stale; the report goes into the build log and somebody — or the `documenter` skill — has to act
  on it. This is the deliberate half of the trade above.
- **A page is only as well-scoped as its `sources:` globs.** A page that declares code it does not
  really document will be reported as stale for changes that do not affect it; the test only
  guarantees that a declared glob matches something, not that the match is meaningful.
- **The translation can lag.** Nothing blocks a merge on a missing or behind translation; the gap
  is reported and recorded. The cost of the alternative (a mandatory translation per page) is paid
  in a language nobody reviews.
- **The docs toolchain is a second dependency set.** It lives in the `docs` dependency group, so
  `uv sync` for an operator does not install MkDocs alongside `torch`.
- **`docs/log.md` grows without bound.** It is text, it is append-only, and the read is a person
  reading the tail; if it ever becomes large, it splits by year rather than being pruned.

## Alternatives considered

- **A wiki or GitHub Docs.** Rejected for the repository copy (already decided in `TODO.md`): a
  wiki does not version with the code and diverges, and GitHub Docs hosts a static set without a
  coverage gate. The guides stay in `docs/`; a wiki can mirror them later, which is an addition,
  not a move.
- **`reviewed: <sha>` in the front matter of every page.** Rejected: the sha of the commit that
  contains the page is unknown while the page is written, so the field would either name the
  previous round (which reads as "reviewed" while the page is part of the change under review) or
  force a second commit that touches every triaged page for no content change. The git-derived
  marker has neither problem and the same information.
- **A committed snapshot of the documented surface** (`docs/_surface.json`) to diff against.
  Rejected for this cycle: `openapi.json`, `migrations/versions/` and `core/config.py` already are
  that inventory, and a second snapshot would be one more generated file to refresh, with its own
  way of going stale. The hook reads the git diff of the files that already exist instead.
- **Blocking CI on freshness.** Rejected: it converts a judgement into a build failure and invites
  the blind bump described above. If the report proves to be ignored, the revisit trigger is a
  *deadline* on the ledger rather than a blocking check.
- **`mkdocstrings` for a generated Python reference.** Rejected: internal docstrings are not a
  curated surface, and the API contract is already generated and gated.
- **Translating everything, including the ADRs.** Rejected: nine historical decision records
  become nine translations to re-verify, and the audience that reads them reads the code.

## Revisit trigger

Reconsider the reporting-only freshness when the ledger shows pages surviving several triage
rounds without being read — that is the signal that a soft report is being ignored, and the answer
is then a deadline on the ledger (for example, a page may not stay unread past one release) rather
than a blocking build. ~~Reconsider publishing with `mike` when there is a first release to serve and
a host to serve it from.~~ **Answered by [ADR 0012](0012-the-documentation-site-is-published-by-ci.md):**
there is a first release and a host, the site is published from CI, and `mike` waits for a second
line supported in parallel instead.

One thing to watch, and it came from the build itself rather than from a plan: MkDocs Material
prints an upstream notice that **MkDocs 2.0 will remove the plugin system and break the theming
overrides, with no migration path**, and that the theme is not licensed for it. If that happens, the
toolchain is re-evaluated. The cost is bounded on purpose: the content is plain Markdown with a
front-matter contract of two keys, so the pages move and only `mkdocs.yml`, the hook and the CI step
are rewritten — which is the reason the tracking was not built into a plugin in the first place.
