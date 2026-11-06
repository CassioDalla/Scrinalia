# ADR 0025: The security policy lives in the application, the proxy terminates TLS

- **Status:** Accepted
- **Date:** 2026-11-05
- **Applies to:** `src/scrinalia/api/security_headers.py`, `src/scrinalia/api/public_rate_limit.py`,
  `src/scrinalia/api/rate_limit.py`, the middleware list in `create_app()`, the `PUBLIC_RATE_LIMIT_*`
  and `SECURITY_HSTS_SECONDS` settings, and the deployment section of `docs/guides/install.md`.
- **Issue:** #259.

## Context

`/api/v1/public/*` is the one surface designed to answer with no session, and 1.8 makes it the public
site. Until this decision it had neither a limit nor a documented header policy:

- the only rate limit was the sign-in brake (`api/login_rate_limit.py`), and the public list/detail
  routes run the same search and facet queries as the curator's reads;
- the only security header was `X-Content-Type-Options: nosniff` on the thumbnail response, and the
  middleware chain carried request correlation and locale only;
- the SPA is served from the same origin by `create_app()` when `apps/curator/dist` exists, so one
  policy covers both the application shell and the public pages.

The question the issue had to settle is **where the policy lives**. A reverse proxy is the usual home
for HSTS and for a global limit, and a proxy can do neither of the things this repository needs: it
cannot be tested against the Vite bundle it would have to allow, and it cannot compose the 429 the
API's clients already read. The alternative — an application that owns everything — is honest about
its own limit: a process-local window is a brake, not a guarantee.

## Decision

### 1. The application owns the header set; the proxy owns TLS

`SecurityHeadersMiddleware` (`api/security_headers.py`) adds, in every response that reaches a route:

| Header | Value |
| --- | --- |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-src 'none'; frame-ancestors 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `no-referrer` |
| `X-Frame-Options` | `DENY` |
| `Strict-Transport-Security` | `max-age=<SECURITY_HSTS_SECONDS>` — only when the setting is positive |

The proxy terminates TLS and nothing else is required of it. It must **not** add a second CSP or a
second `X-Frame-Options`: two policies intersect, and the resulting page can fail in a way neither
configuration explains. The install guide states that boundary; the app cannot enforce it.

### 2. HSTS is opt-in and never binds a subdomain

`SECURITY_HSTS_SECONDS` defaults to `0`, which emits nothing. A plain-HTTP installation on a LAN must
not claim HTTPS, and this is the same reasoning that keeps `AUTH_COOKIE_SECURE` false by default. The
header is `max-age=N` only: `includeSubDomains` and `preload` would bind names outside this
application and cannot be undone from a configuration file once a browser has cached them.

### 3. The `/schema` pages are exempt from the CSP, deliberately

Litestar serves Swagger, Redoc, RapiDoc and Stoplight under `/schema`. Each render plugin loads its
scripts and styles from a CDN and then runs an inline initialiser; a strict `script-src 'self'`
blanks every one of them. The exemption is one prefix, boundary-aware (`/schema*`, not `/schemafoo`),
and the other headers still apply. The alternatives — a relaxed CSP with `'unsafe-inline'` scripts,
or vendoring four UIs — were rejected: the first weakens the page that matters least, the second adds
megabytes to the repository to serve a developer convenience.

### 4. The public surface has a per-process brake, not a global quota

`PublicRateLimitMiddleware` (`api/public_rate_limit.py`) counts requests under `/api/v1/public` with a
sliding window and answers **429** when the address has spent its allowance:

- the window is `PUBLIC_RATE_LIMIT_MAX` per `PUBLIC_RATE_LIMIT_WINDOW_SECONDS` (default 120 per 60 s);
- the refusal is the API's shape — `error_code`, `message` in the request's language and
  `code: PUBLIC_RATE_LIMITED` — plus `Retry-After`;
- a refused hit is not appended, so hammering does not extend the wait, and the window slides, so a
  client that waits is served again without an operator;
- the middleware answers **before** routing, so a flood costs no database work, and
  `RequestContextMiddleware` is outer, so the 429 carries `X-Request-ID` and reaches the access line.

The state is in the process, exactly like the sign-in brake. A deployment that needs one global or
durable ceiling configures it at the proxy; the two are complementary, not alternatives. `uvicorn
--workers N` multiplies the ceiling by N, and `/health/*` and the curator surface are not counted.

### 5. One window implementation

`SlidingWindowLimiter` (`api/rate_limit.py`) is the only window. `LoginRateLimiter` wraps it and turns
a refusal into `TooManyLoginAttemptsError`; the public middleware reads the returned delay and writes
the 429. The mapping is swept past `DEFAULT_MAX_TRACKED_ADDRESSES`, dropping the keys whose hits have
expired, so a public surface cannot grow one deque per address forever.

## Rationale

- **The app is the only place that can test the policy against what it serves.** The CSP was written
  against the built SPA (one external module script, no inline script) and the six computed
  `style={{...}}` attributes that need `style-src 'unsafe-inline'`. A proxy configuration would track
  the asset names Vite emits, and a front-end change would break the page without failing any test
  this repository runs.
- **The refusal has to be the API's.** The 429 is read by `unwrap()` in `apps/curator/src/api/client.ts`
  like every other refusal; a proxy's HTML error page would be a second error shape.
- **A brake that admits it is a brake is safer than a quota that pretends.** The per-process window is
  the same trade-off ADR 0009 accepted for sign-in, and the guide names the multiplication by workers
  and the proxy's `X-Forwarded-For` requirement instead of hiding them.
- **One header set for HTML and JSON removes the second path.** A CSP on JSON is inert, but it means
  the answer to "does this response carry the policy?" is one line, not a media-type table.

## Alternatives rejected

- **Proxy owns the headers and HSTS; the app owns only the brake.** Centralises the policy for a
  deployment running several applications, but the repository cannot exercise the CSP, the SPA's
  inline styles and the asset names would have to be kept in step by hand, and the 429 would still be
  the application's.
- **A nonce-based CSP.** It would require overriding Litestar's Swagger render plugin and injecting a
  nonce into the Vite build; the six inline styles are attributes, which a nonce cannot cover anyway.
- **Vendoring the four OpenAPI UIs.** Megabytes of assets in the repository and a manual update path,
  to avoid a prefix exemption on a page that publishes the already-public contract.
- **A shared rate-limit store (Redis, a table in PostgreSQL).** New infrastructure for an installation
  meant to run offline by one institution; the durable control is the proxy's, and the login's durable
  control is the account lockout column.
- **`'unsafe-inline'` for scripts to make the docs pages work.** That is the one allowance that turns
  a CSP into a decoration, on every page rather than on the four documentation pages.
- **Reusing `TooManyLoginAttemptsError` for the public 429.** The exception lives in the identity
  domain and its sentence is about signing in; a middleware cannot raise it through Litestar's
  exception layer anyway.

## Consequences

- **A path with no route bypasses the middleware.** Litestar applies application middleware to
  matched routes, so a 404 under `/api/v1/public` is not counted and carries no CSP (measured while
  writing this: `/known` received the probe header, `/nope` did not). A 404 has no content to protect
  and costs no query, and the SPA's deep links are matched by the static router, so they are covered.
- **The public limit is per worker.** `uvicorn --workers 4` serves up to four times the configured
  ceiling before any address is refused. The guide says so, and names the proxy as the place for the
  global limit.
- **Behind a proxy, the counted address is the one ASGI sees.** Without `--proxy-headers` and a
  `--forwarded-allow-ips` naming the proxy, every visitor is counted as the proxy and the ceiling is
  effectively global. The guide gives the flags; the code does not guess.
- **The docs pages lose the CSP.** They are the four interactive renderings of a document that
  `/schema` already serves publicly; the XSS surface is the CDN bundles, not this application's data.
- **The thumbnail route no longer sets `nosniff` itself.** One definition in the middleware; the
  integration test that asserted the header still passes, now through the middleware.
- **`PUBLIC_RATE_LIMITED` joins the contract** as a `RouteMessageCode`, an additive change, and
  `bun run contract` must be part of the change.

## Revisit trigger

- **The public site (#46) emits its own inline script or loads a font, an image or an API from
  another origin.** Then `script-src`/`font-src`/`img-src`/`connect-src` need that origin, and the
  decision is whether the second surface is served from this origin at all.
- **The deployment runs more than one API worker and needs a real ceiling.** Move the window to the
  proxy or to a shared store; do not make the per-process number look like a quota.
- **A proxy or CDN starts terminating TLS in front of the app.** HSTS may move there; keep exactly
  one owner of the header, and delete the application's setting if the proxy takes it.
- **A CSP violation is observed in production.** The policy has no `report-to` because there is no
  endpoint that would collect it (ADR 0005: no hosted tracker). Adding one is a new decision, not a
  configuration flag.
