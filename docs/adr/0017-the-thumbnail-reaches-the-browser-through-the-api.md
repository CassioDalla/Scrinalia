# ADR 0017: The thumbnail reaches the browser through the API

- **Status:** Accepted
- **Date:** 2026-10-25
- **Applies to:** the commits that added the authenticated thumbnail route, the `thumbnail_url` of
  the collection read view and the miniature in the curator SPA (#102).

## Context

The `thumbnail` worker completes `storage_thumbnail_uri`: it downloaded the source image and wrote a
JPEG into the configured S3-compatible bucket, **97 of the reference collection's 101 descriptions**
in the run that closed #101. The column is a reference — `s3://meu-bucket-teste/thumbnails/thumb_109222.jpg`
— and the browser can neither resolve it nor is it allowed to: it names a private bucket and a host
that is infrastructure, not the API ([ADR 0003](0003-monorepo-and-curator-frontend-stack.md)).

Three measured facts frame the decision:

1. **The endpoint is the API's private one.** `.env` points `S3_ENDPOINT_URL` at
   `http://localhost:8333`; `docker-compose.yml` points it at `http://host.docker.internal:9000` for
   the container. A presigned URL would hand that host to the browser, which may not resolve it, and
   over HTTPS it would be blocked as mixed content.
2. **The empty state is common, not an edge.** Four descriptions have neither a stored URI nor a
   source image. The screen has to show "sem imagem" for them and "indisponível" when a URI points at
   an object that left the bucket: a URI is a reference, not a guarantee.
3. **The stored object is a miniature.** One object sampled in the local bucket measured **384×249
   and 119,702 bytes**; a page of twenty-five is a few megabytes, not a page of originals. The API
   can carry those bytes; a collection that stores originals would have to revisit that.

The issue also required that the SPA never assemble an API path and never talk to S3. A presigned
URL would satisfy the second half and leave the first to the client (the URL would be built by the
API but the client would need to know when to refresh it); a proxy route satisfies both by handing
the read view one field.

## Decision

### 1. The API serves the bytes, under the session

`GET /api/v1/documents/{description_id}/thumbnail` is an **authenticated, same-origin** read. It
looks up the stored URI, reads the object through `S3Storage.read_object` and returns the bytes with
its image media type (JPEG in practice), `Cache-Control: private, max-age=300` and
`X-Content-Type-Options: nosniff`. The
browser sends the session cookie with the `<img>` request, so the read is authorized by the same
guard as every other route and cannot outlive the session.

The route is a proxy and **not** a redirect to a presigned URL: a presigned URL is a capability
outside the session, valid for its whole lifetime even after the account is disabled, and it names
the bucket's host. The proxy costs API bandwidth — accepted, because the objects are miniatures
(fact 3) and the API is already the only origin the SPA talks to.

### 2. The read view advertises the URL; the client builds nothing

`DocumentSummary.thumbnail_url` is a **computed field** on the server: the API route and the URL are
declared together in `document_schema.py` (`DOCUMENTS_RESOURCE` + `THUMBNAIL_SEGMENT`), so the
controller and the advertised URL cannot drift. It is `null` exactly when there is no stored image.
The front binds it to `src`; it never concatenates a path, never sees the bucket and never needs to
know the route exists.

The raw `storage_thumbnail_uri` stays on the internal read view and on the public projection for now.
The public site (#46) will get a `/api/v1/public/documents/{id}/thumbnail` route that reuses the same
reader and a projection that publishes a URL instead of the raw `s3://` reference. That is a
deliberate follow-up, not a second decision: the reader and the status contract are the same.

### 3. Three states, three answers

> **Amended by [ADR 0022](0022-an-unconfigured-installation-advertises-no-object-backed-url.md):** an
> unconfigured installation now advertises no `thumbnail_url` and answers **404**, not 503; **503**
> is kept for a storage that *is* configured and cannot be read.

- **200** — the stored bytes.
- **404** — no stored URI, no such description, or the URI's object is no longer in the bucket. The
  dossier shows "Sem imagem" or "Imagem indisponível"; it never shows a broken-image glyph.
- **503** — the storage is unconfigured or unreachable. That is an operator problem, not a defect of
  the request; it is logged, and the screen still renders the placeholder.

The API reads the whole object into memory in the handler thread and returns a plain `Response`. A
thumbnail is small, and reading it in the thread keeps the event loop out of boto3; streaming would
move the blocking read into the response iterator.

### 4. The map stays one definition

`S3Storage.read_object` parses the URI's own bucket, not `S3_BUCKET_NAME`: a row written before the
installation moved to another bucket still names the object it stored. A media type that is not
`image/*` is replaced by `image/jpeg` — the worker only writes images, and a bucket's `ContentType`
must not decide what this origin serves.

## Alternatives rejected

- **Presigned GET returned by the API.** Decided against for the host reachability and mixed-content
  problems in fact 1, and because the URL's lifetime is not the session's: disabling an account
  would not end the access it already handed out.
- **Redirect to a presigned URL.** Keeps a stable path, but still embeds the private host, and the
  302's caching semantics are a second, subtler contract for a browser that already caches images.
- **Public-read bucket.** The collection is not public, and the diffusion gate is per record; a
  bucket policy cannot see `is_published`.
- **The SPA building `/api/v1/documents/{id}/thumbnail`.** A second definition of a route the API
  declares, and the exact failure principle III exists to prevent; the front is compiled and the
  path would still be wrong at runtime.
- **Falling back to `original_thumbnail_url`.** Hotlinking the source would leak the reader to a
  third party, break when the source changes its links, and make a removed object look available.
  The archive is the source of what the archive shows.

## Consequences

- **Positive.** The dossier and the collection list show the miniature with no new permission and no
  second origin; the bucket stays private; the session is the access control; the SPA has one field
  to read and no URL to assemble.
- **Cost.** The API carries the image bytes, and the whole object is held in memory per request.
  Accepted for ~120 KB miniatures; revisit if an origin stores full-resolution files or if a public
  site makes the same route hot.
- **Cache.** Images are cached privately for five minutes. A forced thumbnail re-run can take that
  long to replace a bad image on screen; the alternative, `no-store`, would pay the bucket on every
  render of every page.
- **Known gap.** The public projection still publishes the raw `storage_thumbnail_uri` and no public
  route serves it. #46 owns that decision; the reader added here is what it will use.
