# ADR 0009: Authentication by first-party session, authorization by a declared level per operation

- **Status:** Accepted
- **Date:** 2026-10-07
- **Applies to:** the `feat(identity)` and `feat(api)` commits of cycle B9.1 — the `auth_users` and
  `auth_sessions` tables, the `identity` domain, the session guard over `/api/v1` and the access
  classification of every operation.

## Context

Until this cycle, **any client that could reach the API could approve a record, delete a description,
merge two tags and trigger a worker**. The scale is not anecdotal: 85 paths, 100 operations, 58 of
them mutations, and 12 columns of authorship across 12 tables storing free text (`changed_by`,
`requested_by`, `decided_by`, `deleted_by`, `created_by`). The API had no notion of who was asking.

Two facts shaped the problem more than the feature list did.

**The "curator BFF" does not exist as a separate process.** ADR 0003 describes two surfaces and two
BFFs, but the curator's is the Litestar application itself: `asgi.py` mounts `apps/curator/dist` at
`/`. Same origin, no CORS, and the browser is the only client. Whatever mechanism is chosen, it is
first-party — there is no third party to hand a token to.

**`changed_by` was a hole that authentication alone would not close.** Eleven request schemas accept
`changed_by` from the client. Had the session arrived and the field stayed accepted, a signed-in
archivist could write somebody else's name, and the audit trail would be *worse* than before: it
would look trustworthy. Authentication without moving the authorship is a security theatre with a
better costume.

The 1.0 blocker in `TODO.md` asked for the minimum defensible: user and password, `changed_by` from
the token, and the public surface open by design. It left the mechanism open, naming OIDC as the
alternative.

## Decision

### 1. Identity is a domain, not infrastructure

`src/scrinalia/domains/identity/` owns `auth_users`, `auth_sessions`, the password policy, the role
map and the CLI. It is a domain and not a corner of `core/` because `core/` has **no tables**: it
holds configuration, logging, storage and the language profiles, none of which have a lifecycle.
Accounts and sessions have one, they appear in the data model, and they are the subject of a screen.

`DomainException` moved to `core/exceptions.py` in the same commit, and
`domains/archive/exceptions.py` re-exports it. It had to: the HTTP layer registers **one** handler for
the refusals of every domain, and a per-domain base class would escape it and turn a business refusal
into a recorded 500. The class was never archive-specific; only its address was.

### 2. The session is a first-party cookie, and the session lives in the database

`auth_sessions` stores the **SHA-256 of the token**, never the token, and the cookie carries the
opaque value. Three consequences, all of them the reason for the choice:

- a dump of the table cannot be replayed as a cookie;
- `revoked_at` makes "sign out" and "sign out everywhere" real, which a signed stateless cookie
  cannot do before it expires;
- deactivating an account ends its access **immediately**, without waiting for a session to lapse.

The cookie is `HttpOnly` and `SameSite=Lax`. `Secure` is configuration
(`AUTH_COOKIE_SECURE`, default false) and not a constant: over plain HTTP on a LAN the browser drops a
`Secure` cookie **silently**, so the login looks like it worked while nothing is stored. A deployment
behind HTTPS sets it to true.

Argon2id with explicit parameters (RFC 9106's second recommendation: 64 MiB, t=3, p=4), a **decoy
verification** for an address that matches no account, so the answer cannot be told apart by a
stopwatch, and rehash-on-login, so raising the cost reaches the accounts that already exist. The
parameters are settings because an institution must be able to raise them without a code change, and
because a test suite lowering them is cheaper than one paying the production cost on every login.

### 3. Authorization is a declared level per operation, enforced by one guard

Every operation of `/api/v1` declares `opt={"access": Access.X}`, where `X` is `PUBLIC`,
`AUTHENTICATED`, or one of the four permissions: `CURATE`, `CATALOGUE`, `OPERATE`, `ADMIN`. A single
guard registered on the application reads that declaration and enforces it.

The role map lives in code (`domain/permissions.py`), not in a table. An editable permission matrix is
a second place where authorization can be wrong, and it answers a question this system does not have:
an archive needs three answers — who reads, who curates, who operates the installation — not a role
composer. `ADMIN` is not "a curator with more buttons": it owns the accounts and the AI workers,
because triggering a worker costs minutes of CPU and changing its preset changes every future
classification.

**The classification is per handler and cannot be per controller.** Litestar guards are cumulative —
`resolve_guards` walks from controller to handler and *extends*, so a route cannot relax what its
controller declared. A guard on `TaxonomyController` would therefore leak into the reads a `VIEWER`
must reach, and there would be no way to take it back for those routes.

**A structural test is what makes it a rule.** `testing/unit/api/test_route_access.py` walks the built
application and fails when an operation of `/api/v1` declares no level, when the open surface is not
exactly the three expected operations, and when a writing `POST` escapes a write permission. This is
ADR 0003's argument applied to authorization: security by field omission is auditable; security by
"remember to protect the new route" is not.

### 4. The open surface is exactly four things

> **Amended by [ADR 0011](0011-first-run-setup-without-an-open-door.md):** the open surface is now
> **five** operations — the login, the two diffusion routes, and the two first-run setup routes. The
> paragraph below is the record of what was decided in this ADR, not the current count.

`PUBLIC` is declared on three operations — the login and the two diffusion routes — and the routes
outside `/api/v1` are not the guard's business at all: `/health/live`, `/health/ready`, `/schema*` and
the SPA shell. The health probes stay outside the version prefix **and** outside the session, which is
what keeps the orchestrator from needing to know the API version, let alone hold a cookie. The
diffusion surface stays open by design: there, the boundary being protected is *what data exists*, not
who is asking.

### 5. Authorship comes from the session, never from the request

`changed_by` leaves the request schemas. The server derives the author from the session, and the
ledgers gain `changed_by_user_id` (a foreign key with `ON DELETE SET NULL`) while **keeping** the text
they already hold: history is not rewritten, and deleting an account cannot erase the *who* of
decisions that still stand. (The foreign keys and the removal from the schemas are the third commit of
this cycle; the tables are created by the first.)

### 6. Out of scope for 1.0, deliberately

> **Amended by [ADR 0011](0011-first-run-setup-without-an-open-door.md):** the first administrator can
> now also come from the first-run screen, guarded by a table lock rather than by the absence of a
> route. The objection below was about the race, and the race is what ADR 0011 closes. Recovery stays
> where this section puts it: the CLI on the host, with no e-mail and no SMTP.

OIDC/SSO, second factors, e-mail and self-service password recovery. Recovery is the CLI on the host,
which is also how the first administrator is created: a route that creates an administrator when no
account exists is an open door whose only defence is a race on the first deploy.

## Rationale

**Why not a signed stateless cookie.** It is cheaper — no query per request — and it cannot be
revoked. The two things an archive actually asks for, "sign out everywhere" and "this person no longer
works here", would have to wait for an expiry short enough to log people out mid-task.

**Why not a JWT in the front.** There is no third party to hand it to. The SPA is served by the same
application, so a bearer token would exist only to be stored somewhere JavaScript can read it, which
is a step backwards from a cookie the scripts cannot touch.

**Why not OIDC.** It varies by institution, which is precisely the coupling ADR 0008 removed one layer
down: the system is meant to be installed by another institution, offline, without a directory
service. It is a natural **addition** later — a second authentication path in front of the same
session — and not the foundation.

**Why a guard and not a middleware.** The refusal had to be correlated. A middleware runs outside
Litestar's exception-handler layer, so its 401 was produced *after* `RequestContextMiddleware` had
already written the access line: the answer the front sees most often was the one line in the log with
no status code and no `X-Request-ID` echoed. A guard runs inside the route handler, before the handler
body and before dependency resolution, so it refuses just as early and the refusal is traceable like
every other answer.

**Why 403 and not 404 for a refused permission.** The route is documented in the contract and the
client is signed in; hiding its existence hides nothing and turns a misconfigured role into a typo in
the URL. The surface that hides existence is the public one, and the rule there is about unpublished
records, not administrative routes.

**Why the failed-login counter is not enforced yet.** It cannot be written in the request transaction:
a failed login raises, `provide_unit_of_work` rolls back, and the counter is erased by the very
failure it counts. It needs its own committed session, exactly like `archive_worker_runs`. The columns
ship with the table so that work is code, not a migration; the enforcement is B9.3.

## Consequences

**What breaks, on purpose.** The API contract grows four operations and three schemas, and every
existing operation now answers 401 to an anonymous client. The eleven `changed_by` request fields
disappear in the third commit, which is a breaking change for any client that was sending one — and
the only way to make the authorship trustworthy. The 14 integration test files that bring up
`create_app()` now sign in first through a shared fixture.

**What is deferred, and where it is written down.** The accounts screen and the user-management routes
are B9.2. Lockout/backoff, rate limiting, `Origin` checking on mutations and an audit view are B9.3.
The OpenAPI document does **not** declare the cookie security scheme: a global `security` requirement
would also mark the diffusion routes and the health probes as protected, and per-route declarations are
a larger change than this cycle. The contract therefore understates the requirement rather than
stating it wrongly; the gap is known and accepted, and it is named among the accepted limits in the
[operations guide](../guides/operate.md).

**Operational.** A session lookup is one indexed query per authenticated request, on its own short
session; the sliding renewal only writes when the session has been idle (`AUTH_SESSION_TOUCH_MINUTES`),
so a read does not become a write. The guard opens that session through `get_db()`, which is why
`testing/conftest.py` patches `api.security.get_db` as well as the composition root: without it a login
written by the request transaction is looked up in another database and every authenticated test
answers 401.

**What an installer must read.** `AUTH_COOKIE_SECURE` must be true behind HTTPS; leaving it false on a
public deployment sends the session token in clear text. And the first administrator comes from
`uv run python -m scrinalia.domains.identity.cli create --email … --role ADMIN`, which prints a
temporary password and flags the account to change it — or, since
[ADR 0011](0011-first-run-setup-without-an-open-door.md), from the first-run screen while the
installation has no account at all.

## Alternatives considered

- **Permissions in a table.** More flexible, and it moves the review of an authorization change out of
  the diff and into a row nobody versions. Rejected for 1.0; the map is a dict that a later cycle can
  read from the database without changing the guard.
- **A guard per controller.** Less noise in the decorators, and impossible to relax per route (see
  above). Rejected after checking `resolve_guards`.
- **An allowlist of paths in a middleware instead of the route's own `opt`.** It works, and it puts the
  answer to "may an anonymous request through?" in a second place that has to be kept in step with the
  classification. Rejected: one declaration, read by both the guard and the test.
- **No roles in 1.0 — every authenticated account can do everything.** It closes the anonymous hole and
  leaves the difference between "curates a record" and "changes the model every future classification
  runs on" invisible. The classification work is the same either way, so the roles cost nothing extra.
- **Reusing `DomainException` for 401/403.** Rejected: those are answers the API owes a client, and the
  unhandled-failure ledger records defects. A `DomainException` would also be mapped to a 400 by the
  domain handler.

## Revisit trigger

- **An institution asks for SSO/LDAP.** Add a second authentication path that produces the same
  session; do not replace the session with a token.
- **`uvicorn --workers > 1`.** The session table already supports it, and ADR 0004's single-process
  assumption for the worker executor does not. Whoever does that must move the executor out first.
- **A second factor is requested.** The account table has room; the login flow is the place.
- **A hosted deployment behind a proxy that terminates TLS.** `AUTH_COOKIE_SECURE` must be true and
  the proxy must forward the `Host` and scheme correctly, or the cookie will be dropped.
