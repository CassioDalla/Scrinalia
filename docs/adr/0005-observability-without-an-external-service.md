# ADR 0005: Observability without an external service

- **Status:** Accepted
- **Date:** 2026-10-07

## Context

Phase 3 of `TODO.md` listed two observability items and the 1.0 blockers repeated one of
them: error tracking ("Sentry or aggregation by root cause") and an orchestrator `/health`.
What existed when this decision was taken:

- **`GET /api/v1/system/health` answers a person, not an orchestrator.** It counts three
  tables, calls Ollama and does a `HEAD` on the bucket, each with its own two-second
  timeout, and it **always answers 200** — a database that is down is a JSON field, not a
  status code. A Kubernetes probe pointed at it would either restart a healthy container or
  wait seconds on a dead dependency.
- **The execution ledger recorded every failure and grouped none of them.** Forty runs that
  failed for the same reason were forty rows. `str(exc)` was stored, which does not even
  name the exception class — `TimeoutError: boom` and `ValueError: boom` were
  indistinguishable in the text.
- **Nothing recorded a 500 from the API itself.** Only `DomainException` and
  `IntegrityError` had handlers; anything else fell through to Litestar's default and left
  the process as a line in a rotated log file.
- **No request had an identity.** A report of "this screen broke at 14:32" could not be tied
  to the record of the request that broke it.

The choice that shaped everything else: aggregating failures locally, in PostgreSQL, or
sending them to a hosted service.

## Decision

1. **Two orchestrator endpoints, outside `/api/v1` and outside the OpenAPI document.**
   `GET /health/live` touches nothing and answers 200 while the process answers.
   `GET /health/ready` runs `SELECT 1` and answers 200 or **503**. They answer *which
   piece is down* nowhere — that remains the human panel's job.
2. **The readiness probe owns its engine** (`NullPool`, `connect_timeout`,
   `statement_timeout`), because a probe that hangs is indistinguishable from a process
   that is not answering, and widening the shared engine would change every request.
3. **The root cause is a generated column, not an application write.**
   `archive_error_fingerprint(text)` is an `IMMUTABLE` SQL function; `error_fingerprint` is
   `GENERATED ALWAYS AS (public.archive_error_fingerprint(...)) STORED` in **both** the
   execution ledger and the new `archive_api_errors` table.
4. **The stored error text carries the exception class** (`KeyError: 'nome'`), because the
   fingerprint is computed from that text and the class is what keeps two different
   failures with the same sentence apart.
5. **The API's unexpected failures get their own ledger**, written through its own
   committed session by a handler registered under the **500 status code**.
6. **Every request carries an id**: the client's or a generated one, echoed in
   `X-Request-ID`, bound to the log context, and printed once per request in an access line.
   The two health probes are excluded from that line.
7. **Sentry is not adopted.** The aggregation is local and the read is a route:
   `GET /api/v1/system/failures`.

## Rationale

- **The system has to be installable by another institution.** Phase 5 and the backlog are
  explicit about decoupling from this one, and an institution that installs the system
  on-premises, offline, gets no value from a hosted error tracker — it would ship a product
  whose failure visibility depends on an account somebody else owns. Aggregating in the
  database the system already requires means the feature works the day it is installed.
- **A generated column cannot drift from the code that writes the message.** The single
  most likely defect in a fingerprint is a second implementation: a Python function for the
  write and a SQL expression for the backfill, agreeing on the day they are written and
  diverging later. `ADD COLUMN ... GENERATED ... STORED` backfilled the rows that already
  existed with the very expression the new rows get, so the migration contains no
  normalization logic at all.
- **The function had to be SQL anyway.** PostgreSQL refuses a generated column whose
  expression is not `IMMUTABLE`, and `IMMUTABLE` is exactly the guarantee that the value
  PostgreSQL computes once is the value it would compute again.
- **`error_kind` is why the text changed shape.** `str(exc)` is the message only. Without
  the class, the fingerprint merges unrelated failures that happen to share a phrase, and a
  merged root cause is worse than no grouping: it is a confident wrong answer.
- **The 500 status key is not a style choice — it is the only correct registration.**
  Litestar resolves an exception handler by walking the exception's MRO and only falls back
  to the status key for exceptions that are **not** `HTTPException`. Registering the
  catch-all as `Exception` put it in the MRO of `NotFoundException` and turned every
  unknown route into a recorded 500. This was measured, not read: the first version of the
  handler did exactly that and a test caught it.
- **Only unexpected failures are recorded.** A 404, a 409 and a 422 are answers the API
  owes a client. Recording them would fill the screen with the ordinary noise of a
  filled-in form and bury the defect.
- **The probes are excluded from the access line, not from correlation.** An orchestrator
  asks every few seconds; logging each answer would rotate a 50 MB file with "200 OK".
- **The failures read has no grand total.** Groups do not overlap, but summing a worker
  execution and an HTTP request produces a number with two units and no meaning.

## Consequences

Positive: a failure is findable from three directions that agree — the grouped screen, the
ledger row, and the log line, all keyed by the same fingerprint and the same request id; an
orchestrator can be pointed at the API without a special case; and the whole feature works
offline, on the database the system already requires.

Negative, and accepted:

- **No alerting and no paging.** Nothing pushes a failure anywhere; somebody has to open the
  screen. A hosted tracker would page on a new cause out of the box. This is the price of
  the local decision, and it is the reason the ADR exists — the item stays open, deliberately
  deferred rather than silently dropped.
- **`archive_api_errors` grows without a cleanup job**, because the system has no scheduler.
  Growth is bounded by 500s actually happening; the read is windowed by default (30 days) so
  the screen stays cheap regardless.
- **The test schema needs the function.** `testing/conftest.py` creates
  `archive_error_fingerprint` before `Base.metadata.create_all`, the same way it already
  creates `immutable_unaccent`. This is a real, if small, duplication: the DDL lives in the
  migration and in the conftest, and the two must stay identical.

## Alternatives considered

- **Sentry (or an equivalent hosted tracker).** Rejected for this cycle, not forever: it
  adds an external dependency and an account to a system whose value proposition is that an
  institution can install it. The failure data is already in PostgreSQL; a forwarder to a
  hosted service remains possible without changing the write path, which is the useful part
  of having decided this way.
- **A Python pure function for the fingerprint, imported by the migration to backfill.**
  Rejected: no migration in this repository imports application code, and a migration that
  does stops working the day the module is renamed. The generated column removes the backfill
  entirely.
- **Reading the fingerprint from the error text at query time.** Rejected: the normalization
  would run on every row of every read, no index could serve the group-by, and the write path
  would still need the class to be in the text — so the SQL would have to exist anyway.
- **A single `/health` that checks the database.** Rejected: it conflates liveness with
  readiness, so a database restart becomes an API restart. The two failures have different
  correct responses and belong in different probes.
- **Folding the API failures into `archive_worker_runs`.** Rejected: that ledger is about a
  worker *execution* — it has a queue, a concurrency guard and a resolved configuration that
  an HTTP request does not have. Only the fingerprint is shared, and it is shared by being
  the same expression, not by being the same table.

## Revisit trigger

Reconsider the local-only decision when a deployment needs alerting that nobody is watching
for, or when the API is scaled beyond one process and a real operational surface (queues,
retries, a scheduler) exists — at which point forwarding the same fingerprints to a tracker
is an additive change, because the root cause is already a stable key in the database.
