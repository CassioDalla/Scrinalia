# ADR 0024: the open dataset is a versioned projection with a published field map

- **Status:** Accepted
- **Date:** 2026-10-30
- **Applies to:** the commits that move the public projection into the domain and widen it
  (`domains/archive/schemas/public_projection.py`), that add `domains/diffusion/dataset_contract.py`
  and the committed `packages/dataset-contract/v1/`, and the `dataset` adapter, its run and its
  download route (#214, after #251).

## Context

The `dataset` channel is the first `EXPORT` of the diffusion registry (ADR 0023): a snapshot an
institution can host anywhere, generated from the same public projection the site reads. #214 left
four decisions open — the formats, the manifest, the destination and the data license — and the
scope tables it needs landed with #251, so the adapter now has a coverage to read.

The issue also asked a question that hides three different ones: *is this where metadata standards
enter?* They enter at three layers, and mixing them is how an export claims more than it does.

1. **The record.** ISAD(G) is already the model and NOBRADE is already the level ladder. The export
   question is not *whether* a standard, it is which **encoding** and how lossy it is.
2. **The dataset.** Frictionless Data Package, DCAT and schema.org/Dataset describe the *package*:
   publisher, license, resources, hashes, schema. That is a cataloguing decision, not a record one.
3. **The package.** Checksums and a ZIP are integrity, not semantics.

The public projection was also an API module, `api/schemas/public.py`, while the domain worker that
would export it lives in `domains/diffusion`. A domain importing the API layer would invert the
dependency the rest of the repository keeps one-way.

And an export cannot be built from the projection as it stood: it carried the catalogue *name* of
the level (renameable), not the stable code; no source date expression; no extent; no access
conditions. It also carried `storage_thumbnail_uri`, an `s3://bucket/key` that no browser or dataset
consumer can read, while the only thumbnail route is authenticated.

## Decision

### 1. The record is the public projection, and the projection is a domain object

`PublicDocumentSummary`, its nested summaries and the two allowlist frozensets move to
`domains/archive/schemas/public_projection.py`. `api/schemas/public.py` keeps only the page envelope
(`PublicDocumentListResponse`). The dataset schema is generated from that model, never from a second
one: a field is exported because it is in the allowlist, and the allowlist test keeps its exact
partition against `DocumentSummary`.

A per-channel projection stays rejected for the reason ADR 0023 gave: two allowlists to audit, and a
new field public in one channel by accident.

### 2. The projection widens with four fields, and loses the storage URI

| field | ISAD(G) | why the export needs it |
| --- | --- | --- |
| `date_expression` | 3.1.3 | the source's quotation; `document_date` is only the normalized date |
| `level_code` | 3.1.4 | the stable catalogue key; `level` is the label the archivist may rename |
| `dimension_support` | 3.1.5 | extent and medium, a required part of a finding aid |
| `access_conditions` | 4.1 | the conditions governing access, descriptive and not the gate |

`level_code` is derived on read (`ArchiveDocument.level_code`, from `level_ref.code`) and also
travels in `ancestors`, so a consumer can group a branch by the machine key.

`storage_thumbnail_uri` leaves the projection. An `s3://bucket/key` is not an address a public client
can use, and exposing it leaks the bucket and the key; a resolved `thumbnail_url` lands with the
public route (#198), and the dataset will link to it when it exists.

The consequence is deliberate and accepted: the projection is single (ADR 0023), so the public site
and the public API expose these four fields too. The institution took that diffusion decision on
2026-10-30; the `NOT_PUBLIC_FIELDS` comment records it as a dated decision instead of silently
deleting three names.

### 3. Three contracts, one source per concept

- **record** — `PublicDocumentSummary`, generated as `documents.schema.json`;
- **package** — `DatasetManifest`, generated as `manifest.schema.json`;
- **field map** — `field-map.json`, the crosswalk between the JSON field, its ISAD(G) element and the
  serialization convention.

The field map is tested as an **exact partition** of the projection: every exported field names its
ISAD(G) element, or says why it has none. That is the auditable answer to "which metadata standard":
the standard is a published table held to the model by CI, not a paragraph in a guide.

### 4. v1 ships JSON, NDJSON and CSV; EAD3 is its own decision

The consumer is two-sided: an institution's own team building a site (NDJSON/JSON and the field
map), and another archive importing the records (CSV now, EAD3 later). EAD3 is a **hierarchical
finding aid** — `eadid`, a control block, `archdesc` and the components as a `<dsc>/<c>` tree — not a
serialization of a flat list. The dataset projection has no `parent_id` (the branch arrives as
`ancestors`, and the parent is its last rung when the parent is covered), no `physdesc` tree and no
maintenance story. "Skip the record missing a required element" does not fix an orphan component.

So EAD3 is a separate decision with its own minimum profile, RNG validation, orphan rule and AtoM as
its acceptance case. Claiming EAD3 before validating against the schema would be the exact
"confident statement not measured" the constitution forbids.

### 5. The manifest is ours, Data-Package-shaped, not a conformance claim

`manifest.json` carries `schema_version`, a deterministic `snapshot_id` (derived from the ordered
records, **not** from `generated_at`), `previous_snapshot_id`, `generated_at`, `record_count`,
`artifacts[]` with path/bytes/sha256/records, `removals[]`, the data `license`, the `institution`,
the `software` attribution and the links to the live API and its OpenAPI.

`resources[]` is shaped like a Frictionless Data Package so a future `datapackage.json` is a
generated view, not a redesign. It does not claim Frictionless conformance: the manifest carries
semantics the spec does not (removals, snapshot identity), and claiming a standard without validating
against it is worse than not claiming it. DCAT is for harvest by a portal; no portal is in the queue.

### 6. The data license is required, and separate from the software license

The channel refuses to run without a data license, with no default: `CC0-1.0`, `CC-BY-4.0`,
`CC-BY-SA-4.0` or `custom` (which requires a name, a URL and an attribution line). CC BY and CC BY-SA
require the TASL attribution; CC0 does not. CC BY 4.0 is the documented recommendation.

The AGPL-3.0-only plus attribution term (ADR 0006) is the **software** license and says nothing about
the records. The manifest carries both, in separate fields. The software attribution must not become
a second copy of `apps/curator/src/lib/attribution.ts`: either the manifest links to it or the
definition moves to a neutral source both read — a decision of the adapter's commit, not of this one.

### 7. The destination is a local snapshot behind a public door

The run writes `snapshots/<snapshot_id>/` under a configurable directory and flips a `current`
pointer by rename, so a download sees either the previous snapshot or the new one, never a half-written
one. Retention defaults to two snapshots. S3 is a later optional destination, never a requirement
(ADR 0019's boundary); streaming generation is rejected.

The download route is public and **404 when the channel is absent or paused**. The access control is
the curator's coverage, not a login: a researcher downloading an open dataset should not need an
account, and an operator who serves the directory with nginx bypasses API authentication anyway.
Pausing closes the API door; it does not delete copies already downloaded. A private dataset would be
another capability, not a config flag.

### 8. The contract is generated, committed and gated

`packages/dataset-contract/v1/` holds the three generated files. `bun run contract` regenerates them
with the OpenAPI document, CI fails on drift, and the suite compares the committed files with the
models. The gates that matter are tests:

- the field map is an exact partition of the projection;
- an empty covered set produces a valid empty dataset;
- two runs over the same set produce the same hashes and the same `snapshot_id`;
- publish two, export, unpublish one, re-export: the manifest lists the removal and the files no
  longer contain the record;
- a run without a destination or without a license refuses with a sentence;
- a package never carries `storage_thumbnail_uri`.

### 9. Versioning

`v1` is frozen. An additive optional field is a MINOR bump inside it; removing, renaming or retyping a
field is a MAJOR bump and a new directory. Because the record schema is generated from the public
projection, a MAJOR dataset change is also a change to what the public site shows — the single
projection makes that consequence deliberate, and it is the reason a channel cannot quietly widen its
own contract.

### 10. A standard is adopted with a consumer, not ahead of one

No Frictionless, DCAT, BagIt or EAD3 claim in v1. When a consumer asks for one, it is added as a
generated view over the same source and pinned by a test. The field map is the one standard artifact
that ships now, because it is the crosswalk every consumer needs regardless of the envelope.

## Rationale

- **The projection is the contract.** Generating the dataset schema from the public allowlist is what
  makes "a field is public" one decision instead of two, and the exact-partition test is what makes it
  a decision a reviewer sees.
- **The field map answers the standards question honestly.** ISAD(G) is the model; the map publishes
  which element each field encodes and which fields are derived, without pretending a flat JSON is a
  finding aid.
- **EAD3 deferred is the measured choice.** A flat list cannot become a valid finding aid by adding an
  XML writer; the tree, the profile and the validation are the work, and they deserve their own issue.
- **The manifest is not a speculative standard.** It carries what a consumer needs to verify, delete
  and attribute; adopting a spec without a consumer would be a claim we cannot test.
- **Local snapshot, public door.** It requires no storage configuration, makes the run and its ledger
  meaningful, and keeps "host it anywhere" true.

## Consequences

Positive:

- A consumer can read the schema and the field map before downloading a byte, and verify every file by
  hash.
- The public site gains the four ISAD(G) fields for free; the dataset and the site cannot disagree.
- The contract cannot drift from the model without a red suite.
- The adapter is the second export a registry proves itself with, and the AtoM adapter has a precedent
  for "format-specific work is its own issue".

Negative, accepted:

- The public site now shows `access_conditions`, `dimension_support` and `date_expression`. That is the
  institution's diffusion decision, recorded in the allowlist comment and here.
- `storage_thumbnail_uri` is no longer public, so a client that wanted it has nothing until #198 lands
  the resolved URL; no shipped client used it (the public site app is #46).
- The dataset keeps no tombstone: a consumer that misses a run must compare snapshots. The manifest
  says what left since the previous one, not since the beginning of time.
- A package is a full snapshot each time; per-record delta is not in v1.

## Alternatives considered

- **A second dataset model.** Rejected: a field added to the public projection would silently not be
  exported, and the two allowlists would drift.
- **Keep the projection in `api/schemas`.** Rejected: the worker is a domain object; the import would
  point the wrong way, and the dataset is not an HTTP concern.
- **EAD3 in v1.** Rejected for now: it is a tree with a profile and a validation, not a serializer.
- **Frictionless `datapackage.json` as the manifest.** Rejected: it does not carry removals, snapshot
  identity or the software attribution, and emitting both would be two sources for one package.
- **Streaming the ZIP on request.** Rejected: no stable "last run", no ledger meaning, and a large
  collection becomes one long request.
- **S3 as the only destination.** Rejected: storage must stay optional (ADR 0019).
- **Authenticated download.** Rejected: the data is public by construction; the coverage is the gate.

## Revisit trigger

Reconsider if any of these becomes true:

- a consumer needs EAD3 or a harvest protocol (DCAT) in practice, not in anticipation;
- a field the export needs is one the institution refuses to show on the public site, which would make
  the single projection insufficient and reopen ADR 0023's decision;
- the dataset must carry the digital object or a resolved thumbnail URL (#198), which changes the
  package's self-containment;
- a consumer needs per-record deltas, making the full snapshot insufficient;
- the reference collection grows to a size where rendering the preview to a temporary directory or
  keeping two snapshots is no longer acceptable.
