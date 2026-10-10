# ADR 0011: First-run setup — the empty installation creates its administrator once, under a lock

- **Status:** Accepted
- **Date:** 2026-10-09
- **Amends:** [ADR 0009](0009-authentication-and-authorization.md) §4, §6 and the operational
  consequence on how the first administrator is created.
- **Applies to:** the `feat(identity)` and `feat(curator)` commits of cycle 1.1 — `POST /api/v1/setup/admin`,
  `GET /api/v1/setup/status`, the first-run screen and the two lines that move in the open surface.

## Context

ADR 0009 §6 put the first administrator in the CLI and refused a route that creates one:

> a route that creates an administrator when no account exists is an open door whose only defence is
> a race on the first deploy.

That objection is precise, and it is about the **race** and the **window** — not about the convenience.
A guarded design answers it, and the cost of not having one is paid by the installer. Today the first
account comes from `python -m scrinalia.domains.identity.cli create`, which means opening a shell on
the host or `docker compose exec` into the container before the UI can be used at all; and because the
CLI generates the password, it is printed to the terminal and the account carries
`must_change_password=True` so that the password sitting in the scrollback stops being a credential.
The screen is one page of the SPA, and the person installing the system is usually the person who will
sign in.

**The guard proposed for the route does not hold.** The straightforward form — one statement,
`INSERT … SELECT … WHERE NOT EXISTS (SELECT 1 FROM auth_users)` — is *not* atomic. Measured against
PostgreSQL 15 with two concurrent transactions, the first left uncommitted while the second ran:

```sql
-- both sessions, READ COMMITTED
INSERT INTO auth_users (email, …) SELECT 'a@x', … WHERE NOT EXISTS (SELECT 1 FROM auth_users);
```

```
INSERT 0 1     -- session A (holding, uncommitted)
INSERT 0 1     -- session B, inside the window
SELECT count(*) FROM auth_users;  ->  2
```

The second transaction's statement takes its snapshot when the statement starts, and the first
transaction's row is not in it. `NOT EXISTS` is a predicate over a snapshot, not a lock on the table.
Two administrators exist, and the deployment's only defence was that nobody happened to click twice.

Two repairs were measured before choosing, with the same two-session harness:

| repair | outcome |
| --- | --- |
| `LOCK TABLE auth_users IN EXCLUSIVE MODE;` then the same `INSERT … WHERE NOT EXISTS` | session B waits for A to commit, then inserts **0** rows — one administrator, and B is told why |
| `BEGIN ISOLATION LEVEL SERIALIZABLE;` + the single statement | one row, but the **first** transaction is the one aborted (`40001 could not serialize access due to read/write dependencies`), at commit, after the hash was paid for |

The second repair makes the loser the request that arrived first, and it turns a business answer (409)
into a database error that has to be retried to become one. The first makes the loser the request that
arrived second, which is what "somebody already did this" means.

## Decision

### 1. The route exists, and the lock is what guards it

`POST /api/v1/setup/admin` creates the first account **only when `auth_users` is empty**, in one
transaction that takes the lock *before* it evaluates the predicate:

1. `LOCK TABLE auth_users IN EXCLUSIVE MODE` — `EXCLUSIVE` conflicts with itself, so two setup calls
   cannot interleave, and it conflicts with the `ROW EXCLUSIVE` of an ordinary write, so the CLI
   cannot create an account behind the route's back either;
2. `INSERT INTO auth_users (…) SELECT … WHERE NOT EXISTS (SELECT 1 FROM auth_users)`.

A concurrent second call waits on the lock, then evaluates the predicate against a snapshot taken
**after** the first transaction committed, inserts nothing, and answers **409**.

The repository owns this and not the service: it is the one invariant only SQL can hold, exactly like
the unique address it already owns. The service above it decides the policy — the password, the role,
the session — and never sees the lock.

### 2. Once any account exists, the route answers 409 forever

The predicate is `auth_users` is empty. Not "has an active administrator", not "has an account that
can sign in": a predicate that a deactivation could reopen would be a way back to the open door, and
"this installation has been configured" is the fact that must never become false again.

The answer is `SetupAlreadyCompleteError`, a `DomainException` mapped to 409 — a business refusal the
API owes a client, not a defect, so it is not written to the unhandled-failure ledger.

### 3. The empty installation is not a secret; the steady state must not cost a hash

`GET /api/v1/setup/status` (`PUBLIC`) answers `{needs_setup: bool}` and nothing else. The screen has to
decide *before* it has a session, and an installation with no accounts has no secret to protect.

Because that fact is public, the POST's steady state is reachable by anyone: after setup, every call
would otherwise run the password policy and argon2id before discovering the table is not empty.
Measured at the shipped defaults (`AUTH_PASSWORD_TIME_COST=3`, `AUTH_PASSWORD_MEMORY_KIB=65536`,
`AUTH_PASSWORD_PARALLELISM=4`): **~42 ms per hash** on the reference machine. So the service reads
`is_empty()` **before** it hashes, answers 409 on the fast path, and leaves the lock and the predicate
as the guarantee for the one window where a race is possible. The lock is therefore held only while
the installation is genuinely unconfigured — that is, at a moment when there is nobody signed in
whose sign-in it could stall.

### 4. The account is a real account, not a bootstrap

- It is an `ADMIN`: the first account administers the installation, and a weaker first account would
  make the next screen (`/configuracoes/usuarios`) unreachable.
- It does **not** carry `must_change_password`. The person chose that password a second earlier; the
  CLI's flag exists because the CLI *generated* the one it printed, and there is nothing to replace
  here.
- It opens a session, and the route answers the account with the cookie. The person already typed the
  password, and it is the same session code the login uses — not a second path into the session table.
  The route stops answering 201 after its one successful call, so this is the only cookie it ever
  hands out.

The CLI stays, for a headless install and as the way back in, and the install guide documents both
paths. Recovery remains administrator-guided: no e-mail and no SMTP. The e-mail address remains the
account identifier for now.

### 5. The open surface grows by two operations, deliberately

ADR 0009 §4 pinned it to "the login and the two diffusion routes".
`testing/unit/api/test_route_access.py` pins it still — the set now holds five operations, and the
update is part of this diff, in the open, so a sixth can only appear the same way.

## Rationale

**Why not keep the CLI as the only path.** The refusal was never about the convenience; it was about
the race. Once the race is closed with a lock, the remaining exposure is the window itself, and the
window is identical either way: an installation that is reachable and unconfigured can be claimed by
whoever reaches it first, whether the claiming requires a shell or a form. What changes is who can
claim it *legitimately* — and "the installer, from the UI they were told to open" is a smaller ask
than "the installer, with a shell on the host, copying a temporary password out of a terminal".

**Why not `SERIALIZABLE`.** Measured above: it protects the invariant and aborts the wrong request,
and the answer it produces is a database error that only a retry turns into the 409 the client
understands. A retry loop for a once-in-an-installation path is machinery bought to avoid one
`LOCK TABLE`.

**Why a table lock and not `pg_advisory_xact_lock`.** The advisory lock is lighter — it would not
block a sign-in's `last_login_at` write — and it only serializes writers that agree to take it. The
CLI does not, and would not: it is the other path that creates accounts. Locking the table whose
emptiness *is* the predicate needs no cooperation from anyone.

**Why not a bootstrap token the CLI prints.** A one-shot secret in the URL or a header is the CLI with
an extra step, and it puts a credential in the address bar, in the browser history and in the access
log — the three places a one-time secret should never be.

**Why not "declare `POST /api/v1/users` public while the table is empty".** The same guard on the
normal account-creation route makes a route's **permission depend on the data**, which is precisely
what the one-declaration-per-operation rule exists to prevent: the classification would have to be
read twice, and a reader of the diff could no longer tell what a route requires.

## Consequences

**What changes.** The contract grows two operations and two schemas. The install guide's step 6 becomes
two paths instead of one. `AUTH_*` does not change, no table changes, and no migration lands: the
predicate reads a table that already exists.

**What breaks, on purpose.** Nothing that exists — the CLI keeps every command it had. The open
surface test is edited, which is the visible act of opening the surface.

**The accepted cost.** An instance that is exposed to a network before it is configured can be claimed
by whoever reaches it first. That was already true of an unconfigured instance reachable by SSH, and
the mitigation is the same one: configure it before exposing it — now one screen instead of a shell.
The lock closed the race; it cannot close the window, because the window is what "first" means.

**Operational.** The lock is held for the duration of one request, and only while the installation is
unconfigured, so no sign-in can be waiting on it. After the first account exists the route is a single
indexed `SELECT` and a 409.

## Alternatives considered

- **One statement with `WHERE NOT EXISTS`, as proposed.** Measured; two rows. Rejected: it is the
  open door it was meant to close.
- **`SERIALIZABLE` and a retry.** Measured; rejected for aborting the first request and for the retry
  machinery (see above).
- **A unique partial index that admits one row.** PostgreSQL cannot express "at most one row" as a
  constraint — every candidate index has to name a value, and a `(true) WHERE …` index would make the
  *second* account illegal forever, which is the opposite of what the installation needs.
- **The CLI generating the password and the screen only setting it.** Two half-flows, and the
  installer still needs the shell before the screen will render.

## Revisit trigger

- **A hosted deployment that is reachable before it is configured.** The window is the exposure; an
  installation that cannot be reached until the operator says so needs no change, and one that can
  should be created behind the operator's network.
- **A second account provider (OIDC, LDAP) lands.** The first account stops being the bootstrap and
  becomes one more account; this route's `needs_setup` predicate is then about the directory, not the
  table, and the ADR has to be rewritten rather than amended.
