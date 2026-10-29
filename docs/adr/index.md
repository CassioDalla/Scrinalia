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
| [0004](0004-worker-execution-from-the-api.md) | AI workers run from the API process, one at a time, with a run ledger in the database. Superseded by ADR 0014. |
| [0005](0005-observability-without-an-external-service.md) | Failures are aggregated locally in PostgreSQL; there is no hosted tracker and no alerting. |
| [0006](0006-license-and-author-attribution.md) | `AGPL-3.0-only`, plus one additional term under section 7(b) preserving the author attribution, defined once and rendered by the footer. |
| [0007](0007-project-name-scrinalia.md) | The project is named Scrinalia. |
| [0008](0008-language-in-code-and-collection-vocabulary-in-the-database.md) | The language is code, the collection vocabulary is data, and the origin is a parameter with no default. |
| [0009](0009-authentication-and-authorization.md) | First-party sessions in the database, argon2id, three roles, and one access level declared per operation. |
| [0010](0010-documentation-coverage-and-freshness.md) | The documentation is versioned with the code: coverage is a gate, freshness is a report recorded in a ledger. |
| [0011](0011-first-run-setup-without-an-open-door.md) | First-run setup: an empty installation creates its first administrator once, under a table lock, and answers 409 forever after. Amends ADR 0009. |
| [0012](0012-the-documentation-site-is-published-by-ci.md) | The documentation site is published by CI from `main`, into the Pages artifact, latest-only. Amends ADR 0010. |
| [0013](0013-the-tag-axis-is-the-subject-axis.md) | The tag axis is the subject axis: a tag is a drawer or not-a-subject, the place/producer/person cases live on the entity axis, and the exclusion bans the spelling it confirms. |
| [0014](0014-the-workers-leave-the-api.md) | The workers leave the API: the run ledger is the queue, a runner claims with a lease and the database clock, the API only enqueues, and the runner authenticates as a PostgreSQL client. Supersedes ADR 0004. |
| [0015](0015-schedules-and-retries.md) | Schedules are one cron row per worker, a dedicated scheduler holds an advisory lock, and a retry is a new ledger row with `attempt`/`retry_of`/`not_before`. Amends ADR 0014. |
| [0016](0016-the-origin-is-a-first-class-object.md) | The origin is a definition in code plus a row with a lifecycle and an agenda; its code flows through the pipeline and the run ledger, and the ingestion is the stage before the transfer. The manual entry is the origin `manual` and enters the AI flow as `PENDING_AI`. Extends ADR 0008. |
| [0017](0017-the-thumbnail-reaches-the-browser-through-the-api.md) | The miniature reaches the browser through an authenticated API route; the read view advertises its URL and the client builds none, while the bucket stays private and the public surface waits for #46. |
| [0018](0018-trials-and-the-human-gabarito.md) | A trial is a ledger row that runs configurations sequentially over one sample and writes no archival content; the gabarito is the human decision already recorded per axis, never `HUMAN_APPROVED`, and the comparison produces the settings write instead of becoming a second place where the choice lives. |
| [0019](0019-the-csv-import-is-parsed-in-the-browser.md) | The CSV import is parsed in the browser and sent as a bounded list of rows; the `csv` origin has no adapter and no storage, the map and the bounds are published by the API, and the answer is a per-row result. |
| [0020](0020-the-interface-speaks-two-languages.md) | The interface speaks Portuguese and English, the locale follows the account with the browser before it, and the API answers in the requested language; copy lives in one typed catalogue, labels are looked up by the identity the payload carries, and the server translates only its sentences. |
| [0021](0021-the-url-speaks-the-interfaces-language.md) | The URL speaks the interface's language: the screen paths and their query keys stay Portuguese because a path is an identifier and not copy, and the path has one owner in the SPA's screen catalogue. |
