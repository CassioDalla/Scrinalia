# ADR 0019: The CSV import is parsed in the browser and sent as rows

- **Status:** Accepted
- **Date:** 2026-10-25
- **Applies to:** the commit that added the `csv` origin, `GET /api/v1/ingestion/csv/spec`,
  `POST /api/v1/ingestion/csv`, the Importação CSV card and the migration seeding the origin row
  (#191).

## Context

ADR 0016 deferred the CSV import and named the boundary: it must not force object storage into an
ingestion feature (#191). The storage is optional in this installation — the bucket exists for
thumbnails, and an installation can serve every other screen without it — so a CSV that had to be
uploaded to the bucket and read back would make an ingestion write depend on a subsystem the
archivist may never have configured.

The obvious route was a multipart upload. It would have brought a second storage concern, a
temporary file (or a bucket object) that outlives the request, a parser on the server, and a cleanup
story. The issue asked for the opposite: the SPA reads the file locally, validates it, and sends the
rows as JSON.

The manual origin (#44) is the precedent for the write itself: the row is written as the origin's
raw payload, staged through the same transform, and the same `transfer` worker is enqueued. The
archive description is born `PENDING_AI`; the form is not an approval.

## Decision

### 1. The file never leaves the browser

The card parses the CSV with a small client-side parser and sends `POST /api/v1/ingestion/csv` a
bounded list of rows. There is no multipart route, no `UploadFile`, no object written to the bucket
and no temporary file. The only data that crosses the boundary is the row list, and the route does
not persist a filename.

The parser handles what a spreadsheet exports: comma or semicolon (detected from the header, with an
override), quoted fields with `""` as the escape, newlines inside quotes, CRLF, a UTF-8 BOM, and a
Windows-1252 fallback for the files Excel still produces. It is a source file of the SPA and has its
own `bun test` cases, because a parser that is only exercised by a rendered screen is a parser whose
next bug ships.

### 2. The `csv` origin is an origin like the others

`csv` is a definition in code (`OriginKind.CSV`, `CsvOriginConfig`, `CSV_SOURCE_SCHEMA`) plus a row
in `ingestion_origins`, exactly as ADR 0016 prescribes. It has no adapter and no port: the import
route writes and stages the rows itself, and an `ingestion` run of the origin only retries a row an
earlier import could not structure.

`CSV_SOURCE_SCHEMA` maps the **file's headers** to staging columns. The headers are the person's
Portuguese and are payload keys, like a site's labels: they are not translated, and the map is
declared next to the schema. `title` and `document_date` are consumed through `title_key` and
`date_keys`, not `field_map`, or the transform would append the title to itself.

The field set is the manual contract's (`ManualIngestionRequest` minus the identity), and a test pins
the equality: #192 expands both together, and a field added to one without the other fails before it
can file a column as unknown.

### 3. The bounds are one definition, published to the client

`domains/ingestion/csv_import.py` declares `MAX_CSV_ROWS`, `MAX_CSV_BYTES`, `MAX_CSV_ROW_BYTES` and
`MAX_CSV_FIELD_CHARS`, together with the field catalogue. `GET /api/v1/ingestion/csv/spec` publishes
them and the map; the screen refuses a file it can see is too large and validates the rows against
the same catalogue. The route enforces the bounds it can see — the row count and the serialized
payload — and answers **413** with a Portuguese sentence when a request exceeds them. The server
cannot verify the bytes on disk, and does not pretend to: the bound that matters is what the API
receives.

### 4. The API is the authority, and the result is per row

Every row is validated with the same `StagingDocumentDTO` and `SourceSchema` the staging transform
will use. The import is deliberately stricter in two places where the transform is forgiving: a
missing title and a date the language profile cannot read are refusals, because silently becoming
the placeholder title or `None` is the opposite of what an archivist uploading a spreadsheet expects.
A date the profile *does* read (`Década de 1980`, `1951-1953`) is a legitimate date; the grammar
stays in one place.

A duplicated `description_id` — in the batch or already in `raw_data`, `scraping_queue` or the
archive — is a per-row `DUPLICATED`, never a 500 and never an overwrite. A partial import is a normal
outcome: the accepted rows are written as `origin_code='csv'`, staged in one run, and one `transfer`
is enqueued after them. The response reports every row with its file line, status and issue, and the
screen accounts for them.

## Rationale

- **Storage stays optional.** The import path never imports `boto3`, never reads a bucket and never
  needs `S3_*` to be set; the thumbnail bucket remains a feature of the diffusion path, not a
  prerequisite of ingestion.
- **One map, not two.** The spec endpoint, the route's validation and the staging transform read the
  same catalogue, so a header the screen accepts cannot be a column the server files as unknown.
- **The row is the unit.** A file is a convenience; what enters the pipeline is a record with an id,
  a payload and a per-row verdict. That is what makes a partial import honest and a duplicated id a
  sentence instead of an exception.
- **The transfer stays one run.** The ledger has one slot per worker and the transfer already takes
  the whole pending staging set; enqueuing one run per row would multiply slots for nothing.

## Consequences

Positive:

- An installation without object storage imports a CSV exactly like one with it.
- The parser, the map and the row rules have gates in both languages (`bun test` and `pytest`).
- The screen shows what will happen before the write and what did happen after it.

Negative, accepted:

- **Re-importing a file without the `Identificador` column creates new records.** The column is
  optional; the screen generates `csv-<uuid>` per row when it is absent. Updating an existing
  imported record through a re-import is not in this change; the dossier is the way to correct a
  record, and a duplicate id is refused rather than updated.
- **The per-row report is the response, not a durable table.** The durable trail is the raw payload,
  the queue row, the staging record and the `transfer` run; a later screen that wants the history of
  one import needs a ledger of its own.
- **The byte bound is the payload's, not the file's.** The screen checks `File.size` as a courtesy;
  the API can only enforce what it receives.
- **The CSV accepts the manual contract's fields, not all of `StagingDocumentDTO`.** That is the
  deliberate scope of #191; #192 is where both entrances grow together.

## Alternatives considered

- **Upload the file to the thumbnail bucket and read it back.** Rejected: it makes ingestion depend
  on optional storage, adds a temporary object and a cleanup path, and was the concern the issue
  opened with.
- **Send the raw CSV text and parse it on the server.** One parser and one test language, but the SPA
  still has to parse for the preview, so the text path would be a second parser by construction — or
  the preview would not be the server's parse.
- **One `transfer` per row.** Rejected: the ledger's slot is per worker, and the transfer already
  processes the pending staging set in one run.
- **A durable `csv_imports` ledger.** It would give a history and an explicit undo, but it is a new
  table, a new set of gates and a second place where the row's outcome lives; the response is enough
  for the archivist who just uploaded the file, and the pipeline's own tables are the audit trail.
- **All `StagingDocumentDTO` fields now.** Deferred with #192, so the form and the file accept the
  same vocabulary at every step.

## Revisit trigger

- A re-import has to **update** an existing record instead of reporting it duplicated.
- A CSV needs to be kept as a file (for provenance, a retry or an audit).
- The field set outgrows the manual contract before #192 lands.
- A file routinely exceeds the row or byte bound, making a second, asynchronous import path worth
  the queue and the status it would add.
