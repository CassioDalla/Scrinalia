# ADR 0003: Monorepo, generated contract and the curator front-end stack

- **Status:** Accepted
- **Date:** 2026-10-05
- **Fires the revisit trigger of:** ADR 0002 ("reconsider the monorepo when the React frontend
  becomes a second deployable") and ADR 0001 ("OpenAPI-based SDK generation with mature
  generators")

## Context

The Python core is functionally finished: ingestion → staging → archive → AI enrichment → human
curation is verified end to end, and the last two phases (hierarchy, input quality, reversible
merge) were delivered **as API, without UI**, precisely because the Streamlit dashboard is
scheduled for replacement. `TODO.md` has had a single open phase since then (Fase 4), and the
screens it needs are specified in `.analysis/sitemap-front-curador.md`.

Two facts about the existing system shaped this decision, and both were verified rather than
assumed:

- **The contract is already machine-readable.** Litestar serves `/schema/openapi.json` with **63
  operations over 86 named schemas**. The repository already contains a client generator's input;
  writing a client by hand would discard it.
- **`DocumentSummary` leaks curation metadata.** It carries `review_status`, `is_anomaly`,
  `anomaly_reasons`, `archivist_notes` and `provenance`. That is correct for an archivist and
  unacceptable for a public diffusion site: it exposes the internal review process.

ADR 0002 deferred the monorepo because "there is exactly one deployable Python application
today". That is no longer true.

## Decision

1. **Adopt a monorepo, without moving the Python core.**

   ```
   apps/
     curator/            React SPA (the archivist's UI)
     public/             diffusion site (Fase 4 / B7)
   packages/
     api-contract/       openapi.json + schema.d.ts, both committed
   src/scrinalia/   unchanged
   testing/ migrations/ docs/  unchanged
   ```

   `apps/api` is deliberately **not** created yet. Moving `src/scrinalia/api/` is
   cosmetic, and mixing it with the arrival of the UI multiplies the diff for no functional gain.
   It stays a separate, later, movement-only commit.

2. **The contract is generated, and CI fails when it drifts.** A committed `openapi.json` is
   produced from the app and a committed `schema.d.ts` from that JSON. Two CI checks compare both
   against a fresh generation. This is what makes "the API is the stable interface" (AGENTS.md)
   enforceable instead of aspirational.

3. **The curator UI is a client-only SPA.** No server-side rendering. The arguments for SSR —
   indexability, first paint on slow networks, streaming large lists — do not apply to an internal
   tool, while the costs (a Node process to operate, hydration, session handling) would be paid
   immediately. The public surface, where indexability *does* matter, is a separate app and can
   choose differently.

4. **Two surfaces, two BFFs, one domain layer.** The public app reuses the same services and
   differs only in its **output projection**: a `PublicDocumentSummary` with an explicit allowlist.
   Security by field omission is auditable; security by "remember to protect the new route" is not.

5. **Diffusion is its own axis: `is_published`, not `HUMAN_APPROVED`.** Publication is a product
   decision about what to show the world; review is a quality decision about the record. Conflating
   them would mean (a) a typo fix equals publication, and (b) every published document is
   permanently locked against AI rewriting by `ai_writable_documents()`. It also makes the
   curation load tractable: with the materialised arrangement, a whole Série or Fundo can be
   published at once instead of approving 3 608 records one by one.

6. **Stack:** Bun as the package manager and script runner, Vite as the bundler and dev server,
   React 19 + TypeScript, TanStack Router and Query, Tailwind + shadcn/ui. The filter state lives in
   the URL, not in a global store.

## Rationale

**Why the monorepo and not two repositories.** The contract test is the deciding argument: the
generated client must be regenerated from the *same* commit that changes the API, and a blocking
CI check across two repositories requires cross-repo plumbing that does not yet pay for itself. The
`Procfile` and the CI are already single, and the two changes (API and UI) are coupled by design.

**Why Bun does not replace Vite.** These are three separable roles — package manager, script
runtime, bundler — and only the first two are being changed. `bun install` is a drop-in for npm and
its workspaces cover two small apps without Nx or Turborepo. The bundler is left to Vite because
the Tailwind and shadcn/ui ecosystem assumes it; adopting Bun's bundler as well would trade a
mature HMR path for a smaller pond, which is a bad trade for a single-developer project.

**Why TanStack Router rather than React Router.** Every screen in the sitemap is a filtered view:
facets, search term, page and selected tree node all belong in the query string so a link is
shareable and the back button works. TanStack Router's validated, typed search params make an
invalid filter a type error rather than a runtime one, which is the single highest-leverage
convention available for this particular application.

## Consequences

Positive:

- The API gains a consumer that exercises it on every change, which is the cheapest form of
  contract testing available.
- The public surface starts from an allowlist, so a new internal field cannot leak by default.
- `is_published` keeps the AI pipeline able to improve published documents.

Negative, accepted:

- **A second toolchain in CI.** The front-end job needs Node/Bun and the Python job does not; the
  two are deliberately separate so neither waits on the other.
- **Two apps to keep in step with one contract.** Mitigated by the blocking generation checks.
- **The Streamlit dashboard will coexist with the new UI** until B8. Two surfaces showing the same
  data will diverge; the sunset is part of the plan, not an afterthought.
- **`access_conditions` (ISAD(G) 4.1) is currently dropped at the staging → archive transfer.**
  Discovered while specifying this work: the field exists in `domains/staging/` and in neither the
  archive model nor the transfer DTO. Publishing a collection that cannot carry its access
  restrictions is not acceptable, so the column is part of this phase rather than a follow-up.

## Alternatives considered

- **Two repositories.** Rejected: the blocking cross-repo contract check costs more than the
  isolation buys, and there is one deploying institution.
- **Server-rendered React (Next.js or TanStack Start).** Rejected: SSR earns its cost with
  indexability and cold-start latency, neither of which applies to an internal curator tool. The
  public app can revisit this on its own merits.
- **Serving the curator UI from Streamlit or from Litestar templates (Jinja + HTMX).** Rejected:
  the arrangement tree and the preview → apply → undo flows are application interactions, and
  building them without a component model would be more work than the SPA, not less.
- **Keeping `HUMAN_APPROVED` as the publication predicate.** Rejected for the reasons in Decision
  5.
- **A hand-written API client.** Rejected: it discards an already-generated 86-schema contract and
  makes drift invisible.

## Revisit trigger

- Reconsider the separate `apps/api` when `src/scrinalia/api/` needs its own deploy cycle,
  or when the public surface justifies an independent service.
- Reconsider SSR for `apps/public` if the diffusion site is expected to be crawled and the SPA's
  first paint is measured as a problem.
- Reconsider Bun's bundler if Vite becomes a bottleneck or leaves maintenance.
- Reconsider `is_published` if diffusion ever needs more than a boolean (embargo dates, per-field
  restrictions) — at which point `access_conditions` should already be in the archive.

## Update (2026-10-06)

Three statements above are no longer the state of the tree, and one of them was the point of the
plan:

- **The Streamlit dashboard no longer coexists with the curator UI.** It was switched off and
  removed in B8 (`TODO.md`): the app, the dependency, its transitive packages in `uv.lock`, the
  `web` process in the `Procfile` and the `API_BASE_URL` setting it alone read.
- **`access_conditions` is no longer dropped at the transfer.** The column, the DTO and the `PATCH`
  shipped in the cycle that closed this contract (Fase 3.5-C); `access_conditions` and
  `is_published` are both editable from the dossier.
- The generated client is no longer "86 schemas": the committed contract is **128 schemas** after
  the response DTOs of the quality, exclusion and entity routes were typed in the waves 4–6 cycle.
