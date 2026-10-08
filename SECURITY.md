# Security Policy

Scrinalia is archival-description software that an institution installs on its own infrastructure.
A vulnerability here is not only a data leak: it can be a way to alter the historical record, or to
trigger AI work that costs hours of CPU. Reports are welcome and are handled privately.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting** — do not open a public issue, and do not describe
the problem in a discussion:

> **<https://github.com/CassioDalla/scrinalia/security/advisories/new>**

The repository's **Security** tab has the same entry point ("Report a vulnerability"). It opens a
private advisory that only the maintainers can read, and it is where the fix is prepared and the
advisory published once a release carries it.

Please include, as far as you have it:

- the version or commit (`git rev-parse HEAD`) and how the instance is deployed (Docker, bare
  `uvicorn`, behind a reverse proxy);
- what an attacker can do, and what they need to already have (a session? an administrator account?
  network access?);
- the shortest reproduction you can write — a request, a payload, a screen;
- the impact you believe it has, and whether you consider it exploitable in a default install.

If the report involves a **secret that was committed** (a token, a password, a key), say so in the
first line: the secret has to be rotated immediately, and rotation does not remove it from the
history.

## What to expect

This is a small project maintained on a best-effort basis, with no security team and no bug bounty.

- **Acknowledgement:** we aim to reply within **7 days**.
- **Assessment:** we confirm whether it is a vulnerability, and in which versions.
- **Fix and disclosure:** we prepare the fix, and publish the advisory with credit (unless you ask
  to stay anonymous) once a release contains it. If you plan to publish your own write-up, tell us
  and we will agree on a date.

## Supported versions

There is no long-term-support line yet. Security fixes land on `main` and in the **latest release**;
an older release is only patched when an institution is running it and asks.

## In scope

- authentication and session handling: bypassing the guard, forging or replaying a session,
  privilege escalation between the three roles, the lockout or the rate limiter being trivially
  defeated;
- injection of any kind that reaches the database or the filesystem (SQL, path traversal, template
  injection);
- cross-site scripting or request forgery in the curator SPA;
- exposure of a secret through the API, a log line or an error message;
- breaking the governance guarantees the project documents (for example, making an AI worker
  overwrite a `HUMAN_APPROVED` description);
- the public diffusion surface exposing a description that is not `is_published`.

## Out of scope

These are deliberate decisions, documented in the ADRs and the README, not vulnerabilities:

- **`AUTH_COOKIE_SECURE=false`** (the default): it is documented, and a public deployment must set it
  to `true`. Reporting "the cookie is not `Secure`" without a deployment that turned it on is a
  configuration finding.
- **The OpenAPI document (`/schema`) is public.** It is a contract, not a secret.
- **`/api/v1/public/*` is open by design**, and answers 404 (never 403) for an unpublished record.
- **No 2FA, no SSO/OIDC and no e-mail password recovery.** The way back in is the CLI on the host.
- **A single-process assumption:** `uvicorn --workers > 1` corrupts the worker executor's state. It
  is documented in ADR 0004 and in the deployment guide; it is an operational constraint.
- **Denial of service by resource exhaustion on a self-hosted instance** (uploading a huge document,
  triggering a worker in a loop): the account that can do it is already an authenticated
  administrator or curator.
- **A dependency advisory with no reachable path** in this code, or one that requires an attacker to
  already control the installation.
- **Self-XSS**, missing security headers that no browser relies on here, and findings that require
  the attacker to run code in their own browser session.

## Hardening an installation

The three settings that matter most before exposing an instance, all documented in `README.md` and
`.env.example`:

1. `AUTH_COOKIE_SECURE=true` behind HTTPS;
2. `AUTH_TRUSTED_ORIGINS` set to the public origin when a reverse proxy rewrites `Host`;
3. the first administrator created with
   `uv run python -m scrinalia.domains.identity.cli create …` and its temporary password replaced at
   the first sign-in.
