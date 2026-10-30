# ADR 0023: Diffusion is a channel registry, and a record is exposed through a channel scope

- **Status:** Accepted
- **Date:** 2026-10-29
- **Applies to:** the commits that add `diffusion_channels` and the channel registry/lifecycle API
  (#211), the `diffusion_channel_scopes`/`diffusion_channel_exclusions` tables, the
  `archive_document_channels` view and the Difusão page (#251), the Canais de difusão page (#213),
  and the public site's `public_site` read (#46).

## Context

The archive has one diffusion gate: `is_published`, a per-record boolean separate from
`review_status`. The dossier edits it with a checkbox, the public API filters on it in the server,
and nothing is published by default — the collection that #46 would announce is **0 of 4,844**.

The gate answers **whether** a record may leave. It cannot answer **where** it goes, and the owner's
product decision is per destination:

- "Fundo A" goes to channel A, "Dossiê B" to channel C.
- Publishing a parent covers its approved descendants, including a child approved later; one child
  can be overridden and kept private.
- The operator installs and configures the channels; the curator decides what each channel
  receives. They are different permissions and different screens.

#210 proposed the first half of the answer: a channel is a definition in code plus a lifecycle row,
the mirror of ADR 0016's origin. That decision is still right, and it is recorded here together with
the half it did not decide. A registry alone says where the published set goes; it cannot say that
one branch goes to one channel and another branch to another. A per-record assignment could, but the
"a child approved later enters automatically" requirement would then need a policy table and a
worker to materialise it.

The archive already has the unit the owner is naming: the arrangement node. A scope over a node is
the decision "this branch is published here", and the coverage of its approved descendants is a
read, not a write.

## Decision

### 1. A channel is a definition in code plus a lifecycle row

`domains/diffusion/diffusion_registry.py` holds the cheap definition: `code`, label, description,
`capability` (`LIVE` or `EXPORT`), the Pydantic model of the configuration and the field metadata the
operator screen renders. The runtime adapter, when a channel has one, is resolved only by a run, the
way `domains/ingestion/origins.py` is resolved only by an ingestion run.

`diffusion_channels` is the lifecycle: `enabled`, `config` (JSONB, validated by the channel's own
model), `options` (the run policy an export channel inherits), `cron`/`timezone`/`next_run_at`
and the `last_*` facts, plus the author of the last change. There is **no seed**: a fresh installation
has no channel, so the empty state on the operator page is real. `configured` distinguishes "never
added" from "paused"; `enabled=false` is a pause, not an absence.

The registry only ships channels that work. `public_site` is `LIVE` and lands with #211; the dataset
and AtoM are `EXPORT` and land with their adapters (#214; AtoM is a future decision). A channel in
the picker that answers 501 is not a channel.

`config` is **never a secret**. The AtoM token and any storage credential are named by an environment
variable in the config, never stored in the JSONB, so a backup and the dossier's revision history do
not carry them.

### 2. A record is exposed through a scope, not a boolean

Two tables with the same shape, one positive and one negative:

- `diffusion_channel_scopes` — `channel_code`, `node_id`, `include_descendants`, the author and the
  revocation columns, and a note;
- `diffusion_channel_exclusions` — the same shape plus a reason.

A description is exposed on a channel when **all three** hold:

1. its `review_status` is `HUMAN_APPROVED`;
2. a positive scope of that channel covers it (the node itself, or an ancestor whose
   `include_descendants` is true);
3. no negative scope of that channel covers it.

The coverage is calculated on read, from the node's materialised `path`: a child approved after the
scope was created is covered because it is under the same branch, and the exclusion is the one
per-record or per-subtree override. "Fundo A no canal A" is one positive scope on the fundo;
"Dossiê B no canal C" is one positive scope on the dossier; "manter este filho privado" is a negative
scope on the child.

The scope is the curator's editorial decision. The operator configures the channel; the operator
does not choose which records it carries. A channel is not a distribution list that the operator
fills; it is a destination the curator publishes to.

### 3. `is_published` is derived from the coverage

The coverage is one definition, `archive_document_channels` (`description_id`, `channel_code`), a
view over the documents, the two scope tables and the path. `is_published` means "covered by at
least one channel" and is computed from that view, not stored as a column.

The consequences are deliberate:

- `DocumentSummary.is_published` is derived; `DocumentSummary.channels` is the list the dossier and
  the publication screen show.
- `DocumentUpdateRequest` and `DocumentReviewCommand` lose `is_published`; the dossier's checkbox
  leaves the review form. Otherwise a save would keep approving a record in order to publish it —
  the defect that made the old checkbox unable to honour "publishing is not a lock".
- The public search, the public detail route, the counts and the inbox read the same view.
- The `archive_documents.is_published` column is dropped. The old deletion snapshots and revision
  JSON keep the key they recorded; the new writes do not have it.

The approval and the publication stay different decisions. A record approved and not covered is not
public; a record covered and not approved is not public either. Publishing does not change
`review_status`, so it does not lock the AI; a published record is `HUMAN_APPROVED` because the
coverage requires it, and that approval is what blocks the AI, not the publication.

### 4. The public site reads the `public_site` channel; the dataset reads its own

The existing `GET /api/v1/public/documents` served the union of every `is_published` record. That
union cannot express "Dossiê B only in channel C": B would appear on the public site. So the public
site's routes filter the **`public_site`** channel (approved + covered, server-side), and the
dataset's export filters the **dataset** channel. There is no public union.

- `GET /api/v1/public/documents` and the detail route read `public_site`; an id outside the channel
  is **404**, never 403.
- `GET /api/v1/public/site` (#211) returns the `public_site` identity (title, description,
  institution, contact, logo, locale, base URL, indexing) when the channel is enabled, and **404**
  when it is not.
- The dataset is a snapshot of the `dataset` channel (#214); a custom site consumes the dataset, not
  a live union. AtoM, when it lands, is another export of its own channel.
- The `PublicDocumentSummary` allowlist, the facets and `NOT_PUBLIC_FIELDS` stay the single public
  projection. `channels` joins `NOT_PUBLIC_FIELDS`: a channel assignment is curation metadata, not a
  description of the record.

This reverses #210's "the public API is the live read, not a channel". The reversal is the point: a
shared union exposes a record on a surface its curator did not choose. The public API is the live
read of the `public_site` channel, and the dataset is the "build your own site" path.

### 5. The write is a batch of scope changes with a ledger

Publishing a branch or a selection is one command with a preview and an apply:

- **Preview:** resolves the branch, expands the approved descendants, applies the exclusions and the
  already-covered records, and returns the eligible count, the sample and what it skips — without
  writing. A selection token identifies the resolved set so the apply cannot silently run over a
  different one.
- **Apply:** creates the positive scopes (or the negative ones, or revokes them) and records a
  `diffusion_publication_batches` row with its entries: channel, node snapshot, `include_descendants`,
  previous and new state, author, date and note.
- **Undo:** removes the scopes the batch created, reactivates the ones it revoked, skips a scope that
  changed since, and reports both numbers.

Three different removals, not one ambiguous button:

- **Retirar do canal:** a negative scope on the record (or subtree) for that channel; the record
  remains covered by its other channels.
- **Retirar de todos:** a negative scope for every channel whose coverage includes the record.
- **Retirar o ramo:** revokes the positive scope; every record it covered loses that channel.

The ledger records the decision at the scope level, which is the human decision. The per-record
exposure is derived, so "who published this record" is answered by the scope's author and the batch,
not by a row per record.

### 6. Two surfaces, two permissions

- **Canais de difusão** — a card in `/configuracoes` under *Operação*, `OPERATE`, mirroring the
  origins page (#213): add a definition, configure it, enable/pause it, set its agenda (#211), enqueue
  a run (#212), and for `public_site` link to the site when `public_base_url` is set.
- **Difusão** — a top-level entry, `CURATE` (#251): *A publicar*, *Publicadas*, *Publicações por
  ramo* and *Histórico*; a branch filter, the channel picker, the preview, the exclusions, the batch
  ledger and the undo. The page shows only configured and enabled channels; a paused channel does not
  enter the picker, and what is already there is marked paused.
- The Início card for approved records with no channel appears only when a configured and enabled
  channel exists; without a channel there is nowhere to publish, and the card would send the curator
  to an empty screen.

The operator can configure a channel with nothing published, and the curator can publish with no
channel configured in the sense that the queue is empty — the two decisions are independent, which
is #210's "the gate and the channel are different" read one layer out: the approval is not the
channel, and the channel is not the approval.

### 7. The export run reuses the worker ledger

`diffusion` is a worker with a `channel_code` axis in `archive_worker_runs`, claimed by the same
runner, lease and retry as every other execution (#212). A `LIVE` channel has no run: the site is read
on every request, and its "preview" is the public API. The export's dry-run follows principle VI and
reports the record count, formats, destination and removals before it writes; the snapshot is a pure
function of the covered set plus the configuration.

## Rationale

- **The branch is the archival unit.** The owner says "Fundo A", not "these 128 rows": a scope on the
  node is the decision, and the coverage of its children is a read. A per-record assignment would
  make the same decision once per row and need a worker to keep the future children in step.
- **The derived gate removes a state that cannot be explained.** With a boolean permission plus a
  channel assignment, a record can be "published but on no channel"; the screen has to explain it and
  the public API has to decide whether to show it. With coverage as the gate, that state does not
  exist.
- **The public site must be the site's channel.** A union is not a distribution decision; it exposes
  every record any curator published anywhere. The per-channel read is the only way to honour the
  owner's example.
- **The operator/curator split is the permission model.** Configuring a channel is `OPERATE`;
  publishing is `CURATE`. One screen with two audiences, as #213 originally proposed, would either
  hide half the page or widen the permission.
- **The ledger is the constitution's principle VI.** A write with no undo is gated by a preview, and
  every write leaves a ledger; the batch of scopes is the reversible unit.

## Consequences

Positive:

- One screen publishes a fundo, a série, a dossier or a selection to one or more channels, with a
  preview and an undo.
- A child approved later enters its parent's channels without a second run or a second human act;
  the exclusion is the deliberate override.
- The public site, the dataset and AtoM each read their own channel; the single projection stays the
  allowlist.
- The channel lifecycle mirrors the origins: add, configure, pause, schedule, run and attribute, with
  the same panel grammar.
- The dossier no longer publishes by approving; the distinction between review and publication is
  finally true in the code and not only in the guide.

Negative, accepted:

- **The `is_published` column is dropped.** The migration, the search query, the public detail route,
  the facets, the deletion snapshots and the revision JSON all move. The 0-published collection makes
  the data migration safe; the old snapshots keep the key they recorded and the new ones do not.
- **The public API's gate changes.** `published_only` becomes the `public_site` coverage; the 404
  stays. #210's "the live API is the union" is amended.
- **The view is the hot path.** The coverage predicate joins the materialised path; the scopes are
  few and the path is indexed, but the public search and the counts pay for it. If a measurement says
  otherwise, a materialised `archive_document_channels` is the revisit, not a return to the boolean.
- **A negative scope overrides a positive one.** A node can be covered by a branch scope and excluded
  for one child; the service prevents a redundant positive and negative on the same node, and the
  partial unique indexes make the duplicate impossible.
- **The node's path moves.** A scope follows the node's current path, so moving a branch moves what
  it covers; deleting a node cascades its scopes, and the ledger keeps the snapshot. A test pins the
  move.
- **The public `ancestors` and `children_count` are not channel-filtered.** A public child can show
  a parent title that is not itself exposed on that channel; that is a #46 presentation decision, not
  a reason to make the projection per channel.
- **The `public_site` channel can be disabled or absent.** `GET /public/site` answers 404; the site
  app is not deployed; the documents route's behaviour with the channel disabled is part of #46/#211,
  and the empty state of the site is the 0-covered set.
- **The docs and the `search` rule file** say `is_published` is the public predicate; both change to
  the channel scope, and the `NOT_PUBLIC_FIELDS` partition gains `channels`.

## Alternatives considered

- **A per-record `diffusion_channel_documents` table plus the `is_published` permission.** The #210
  two-level model. It preserves the boolean and the column, and the ledger is per record. Rejected
  because the "child approved later enters automatically" would need a rule table and a worker to
  materialise it, and because the branch — the unit the owner names — would be a loop over rows.
- **A per-record assignment with `is_published` derived (the union).** Simpler than the scope but
  still row-by-row, and the union still leaks a record to a channel the curator did not choose.
- **A channel-scoped configuration, with no curator scopes.** The operator sets "channel A = Fundo A"
  and the curator only approves records. It makes the operator the distribution decision, which is
  the opposite of the permission split, and it cannot express a one-off dossier on channel C.
- **The public API as the union.** Keeps #210's live read untouched, but "Dossiê B only in C" is
  impossible: B appears on the site. Rejected by the owner's example.
- **A per-channel projection.** Two allowlists to audit, and a new field would be private in one
  channel and public in another by accident; the exact-partition test would have to become a matrix.
  Rejected.
- **A separate diffusion ledger.** Duplicates the lease, retry, cancellation and failure fingerprint;
  #212 reuses `archive_worker_runs`.
- **The `is_published` column kept as a cache.** It would be stale for the child approved later
  unless a worker updates it; the view is the one definition. Revisit only if the view's measurement
  demands a materialisation.
- **AtoM in the first release.** Deferred, not rejected: the registry must prove a second export
  adapter first; the AtoM mechanism is a research task.

## Amendment — 2026-10-30: the views as implemented (#251)

Three details of §3 were settled when the scopes landed, and the measurement was taken twice.

- **The views name the covering scope.** `archive_document_channels` returns (`description_id`,
  `channel_code`, `scope_id`) — still one row per pair, with the *nearest* scope as the origin: the
  fundo's scope for a dossier nobody scoped directly, the dossier's for one that is. The pair stays
  unique, so the dataset (#214) still filters `channel_code = 'dataset'`; the extra column is what
  lets the curator's page say "pelo ramo do Fundo A" without a second definition of the predicate.
- **The negative set is its own view.** `archive_document_channel_exclusions` answers the same trio
  for the exclusions, and the coverage view composes it instead of repeating the exclusion clause.
  The split is what lets the preview say *why* a record is skipped — "excluded" and not "not
  covered" — without a second implementation of the predicate.
- **The branch is expanded from the path, not matched with `LIKE`.** `path LIKE node_path || '.%'`
  builds the pattern per scope, so the planner compares every approved description against every
  scope. On one seeded collection — 48 050 descriptions, 50 scopes, 100 exclusions, both views
  answering 34 850 rows — the public predicate took **1 146 ms** and the whole channel read
  **1 061 ms**. Expanding each description into its ancestors and joining the scopes on the node id
  is linear in the coverage: **275 ms** and **184 ms** on the same collection, and **5–48 ms** for
  the page's reads on 4 910 descriptions. The split assumes a description id carries no dot — the
  same assumption `build_path` and the dossier's ancestor resolution already make.
- **The views do not read `enabled`.** A paused channel keeps its coverage, the page marks it paused,
  and the public surface is the one that refuses to serve it.
- **The materialised table remains the revisit.** At 48 050 the header counts take **180 ms** and
  the covered list **556 ms**, and both grow with the collection; a materialised
  `archive_document_channels` is the answer if an installation's reference collection reaches that
  size.

## Revisit trigger

Reconsider if any of these becomes true:

- the coverage view cannot answer the public search within an acceptable budget on the reference
  collection, and a materialised `archive_document_channels` is needed;
- a channel needs a field policy narrower or wider than the public allowlist, making the single
  projection insufficient;
- a legal access restriction needs a **permission** independent of the channel coverage, reviving the
  two-level `is_published` permission instead of the derived flag;
- the public site's `ancestors`/`children_count` must be filtered by the channel, which would make the
  projection channel-aware;
- a channel needs a scope the curator cannot express with a node and `include_descendants` (a tag
  scope, a date window), and the scope table grows a second dimension;
- a node move makes the read-time coverage too expensive, and the scope has to store the path it
  covered at creation.
