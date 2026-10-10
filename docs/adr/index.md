# Architecture decisions

Each ADR records a decision that was taken, the alternatives that were rejected, and the
consequences that were accepted. They are written in English and are **not translated**: they are
the reasoning of the code, read by whoever reads the code, and a translated ADR would be a second
record of the same decision (ADR 0010).

Read the one that touches what you are about to change *before* changing it — several of them exist
because the obvious alternative was measured and lost.

| ADR | Decides |
| --- | --- |
| [0001](0001-litestar-as-http-framework.md) | Litestar is the HTTP framework, not FastAPI. |
| [0002](0002-src-layout-and-internal-namespace.md) | The code lives in `src/scrinalia` as one internal namespace; `testing/`, `migrations/` and `docs/` stay outside the installed package. |
| [0003](0003-monorepo-and-curator-frontend-stack.md) | One monorepo, an OpenAPI contract that is generated and committed, and a React + Vite SPA managed by Bun. |
| [0004](0004-worker-execution-from-the-api.md) | AI workers run from the API process, one at a time, with a run ledger in the database. |
| [0005](0005-observability-without-an-external-service.md) | Failures are aggregated locally in PostgreSQL; there is no hosted tracker and no alerting. |
| [0006](0006-license-and-author-attribution.md) | `AGPL-3.0-only`, plus one additional term under section 7(b) preserving the author attribution, defined once and rendered by the footer. |
| [0007](0007-project-name-scrinalia.md) | The project is named Scrinalia. |
| [0008](0008-language-in-code-and-collection-vocabulary-in-the-database.md) | The language is code, the collection vocabulary is data, and the origin is a parameter with no default. |
| [0009](0009-authentication-and-authorization.md) | First-party sessions in the database, argon2id, three roles, and one access level declared per operation. |
| [0010](0010-documentation-coverage-and-freshness.md) | The documentation is versioned with the code: coverage is a gate, freshness is a report recorded in a ledger. |
| [0011](0011-first-run-setup-without-an-open-door.md) | First-run setup: an empty installation creates its first administrator once, under a table lock, and answers 409 forever after. Amends ADR 0009. |
| [0012](0012-the-documentation-site-is-published-by-ci.md) | The documentation site is published by CI from `main`, into the Pages artifact, latest-only. Amends ADR 0010. |
