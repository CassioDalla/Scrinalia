# ADR 0022: An unconfigured installation advertises no object-backed URL

- **Status:** Accepted
- **Date:** 2026-10-29
- **Amends:** [ADR 0017](0017-the-thumbnail-reaches-the-browser-through-the-api.md) §2 and §3.
- **Applies to:** `src/scrinalia/core/config.py` (`storage_configured`), `S3Storage`'s client,
  `DocumentSummary.thumbnail_url`, `GET /api/v1/documents/{id}/thumbnail` and the rules a future
  object-backed field (#198) inherits.

## Context

The API is designed to start without object storage: `provide_thumbnail_reader` imports `S3Storage`
locally and is cached, so boot does not pay boto3. What was missing was the **contract-level**
behaviour, and the gap had three shapes (#258):

1. `DocumentSummary.thumbnail_url` was derived from `storage_thumbnail_uri` alone. A collection page
   advertised one URL per row that carried a URI, the SPA bound each to an `<img>`, and every request
   reached the route.
2. The route answered **503** and logged an exception for every image, because `S3Storage` built its
   boto3 client in `__init__` and only then discovered that there was no endpoint. An installation
   with no storage paid a client, one stack trace per thumbnail and one placeholder per card.
3. "Configured" was defined twice — `system_health.probe_storage` and
   `S3Storage._require_configuration` — with different tests (`is None` versus truthiness), so the
   panel and the reader could disagree. #198 will add a second object-backed field and a second route
   and would have had to remember the same guard.

A row can carry a `storage_thumbnail_uri` in an installation whose `S3_*` settings are absent: that
is the normal state after a database is copied from an installation that had storage, or after an
operator removes the bucket configuration while keeping the database. The URI is a reference, and
the old contract published it as if this installation could resolve it.

## Decision

### 1. One predicate defines "configured"

`core/config.py` owns `missing_storage_settings()` and `storage_configured()` over the four settings
(`S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`). The health probe,
`S3Storage._require_configuration` and the read view all call it, so an empty credential cannot be
configured on one screen and missing in the reader. It lives in `config` and not in `storage` because
`storage` imports boto3 at module level and the read view must not pay it.

### 2. An object-backed field is advertised only when the storage is configured

`DocumentSummary.thumbnail_url` is `None` when `storage_configured()` is false, even when the row
carries a `storage_thumbnail_uri`. The SPA then draws its existing "sem imagem" placeholder and
issues no request. This is the rule for every future object-backed field (#198), not a special case
for thumbnails: the contract never hands a client a URL this installation cannot serve.

### 3. An unconfigured route answers 404, and only a configured failure answers 503

`GET /api/v1/documents/{id}/thumbnail` checks the predicate **before** the URI lookup and answers
**404** when it is false. That is the honest answer for a request that arrives in an installation
which advertises no thumbnail: a stale link has no image, and there is no operator incident to
report per image. The health panel is where "the storage is not configured" is reported, once, with
the missing settings named.

**503 stays** for the case it was written for: the storage **is** configured and the read failed for
a reason that is not a missing key — an unreachable endpoint, a refused credential, a bucket that
cannot be read. That one is an operator problem and keeps its log line.

### 4. The client is built on first use

`S3Storage` builds its boto3 client lazily (`cached_property`) instead of in `__init__`, so
constructing the reader — which the dependency provider does on the first thumbnail request, before
the handler can check the predicate — costs no boto3 import of the client and no client object. The
provider's cache still pays it once per process for an installation that has storage.

## Rationale

- **The contract must not lie.** A URL in a response is a promise; the 404 that follows it is not a
  screen state the SPA can distinguish from "the object left the bucket", and the operator's log
  fills with one stack trace per card for an installation that is working as configured. Null is the
  only value that says "this installation has no such object".
- **The status distinguishes two different situations.** "There is no storage in this installation"
  is a property of the installation; "the storage is configured and did not answer" is an incident.
  ADR 0017 folded them into 503 because only the second existed in its context; the first is now the
  more common deployment.
- **The rule has to live where the next route reads it.** #198 adds a digital-object route and field.
  A predicate plus the assertion that a field is advertised only when configured makes the next
  route inherit the guard instead of re-deriving it.

## Alternatives rejected

- **Keep advertising the URL and keep answering 503.** The page still issues one request per card,
  each with a stack trace and a client, for an installation that has no storage. The SPA shows
  "indisponível" where the truth is "this installation does not keep images".
- **Keep the two "configured" checks and make them match by hand.** The pair had already drifted
  (`is None` versus truthiness); a second object field would add a third caller and a third chance
  to drift.
- **Build the client in `__init__` and check the predicate only in the route.** The provider builds
  the reader before the handler runs, so the unconfigured path would still construct a boto3 client.
- **Answer 503 for an unconfigured installation with no log line.** The status still tells the SPA
  an operator incident exists, and it would make the health panel and the route disagree about
  whether the installation is configured.
- **Have the SPA hide the field when the URL 404s.** A client deciding what the server can serve is
  a second definition of the contract (principle III); the server already knows.

## Consequences

- **The read view's value depends on the installation's configuration.** `thumbnail_url` is `null`
  on a machine without storage and a path on a machine with it, for the same row. That is accepted:
  the field describes what *this* installation serves, and the OpenAPI type does not change.
- **A database restored without its storage loses the on-screen miniatures until the four settings
  are back.** The URI stays in the row; the worker and the route start serving it again as soon as
  `storage_configured()` is true. This is the intended behaviour of the backup guide's "restore the
  database and the bucket as a pair": the pair is what makes the pictures visible.
- **The health panel becomes the one place that names the missing settings**, and it names them
  individually instead of a generic "endpoint, bucket or credentials".
- **Tests must state the storage configuration instead of inheriting it from `.env`.** The thumbnail
  route tests set the four settings (or clear them) explicitly, so a developer's `.env` cannot hide
  the unconfigured case.
- **The public projection is unchanged.** It still publishes `storage_thumbnail_uri` and no URL;
  #46 owns the public route and inherits this rule when it adds one.

## Revisit trigger

- An installation where object storage becomes mandatory (for example, every description must have
  a digital object). Then "unconfigured" would be a boot failure, not a valid state.
- A second consumer that needs to distinguish "no storage" from "no object" in the response body
  rather than from the installation's health. The 404 detail already names the difference; a code
  would need the `RouteResponse` treatment.
