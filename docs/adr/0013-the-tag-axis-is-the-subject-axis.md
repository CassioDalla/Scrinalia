# ADR 0013: The tag axis is the subject axis, and "not a subject" is routing rather than a third axis

- **Status:** Accepted
- **Date:** 2026-10-13
- **Amends:** the recorded reasoning in `models/taxonomy.py` (`ArchiveTagFacet`, whose class docstring
  makes the producer/place axis a state of a tag) and in `domain/vocabulary.py` (`is_place_term`'s
  claim that the PLACE facet is where a street "goes"); and [ADR 0008](0008-language-in-code-and-collection-vocabulary-in-the-database.md)
  §2, where a place kind "claims the PLACE facet" — the distinction it draws is kept, the destination
  moves to the entity axis.
- **Applies to:** the `archive_tag_facets` table and the `TagFacetType` / `TagCatalogState.FACET`
  states, `Repository/TagService` facet methods, the `PUT`/`DELETE /api/v1/taxonomy/tags/{tag_id}/facets/{facet_type}`
  routes, `domain_subject_exclusions`, `domain_stopwords`, the tag catalogue of the curator SPA and
  `guides/curate.md`. Closes issues #83 and #84.

## Context

`archive_tags.macro_category_id` answers *what is this about?*. `ArchiveTagFacet` was added so that a
tag with no honest answer to that question could instead answer a different one — `alfa` is *who
produced*, `cidade` is *where* — because forcing those terms into a subject drawer was a measured cause
of the systematic misclassification (`alvenaria` landing in "Mobilidade e Transporte", from the
vocabulary module's own record). Measured in this checkout, the axis was built but never used:

| measured | value |
| --- | --- |
| rows in `archive_tag_facets` | **0** in the reference collection (`scrinalia_zeroed`, 101 descriptions), **1** in `memoriacuritibana` |
| readers of the table | the tag catalogue's own state chip (`repository/subject_queue.subject_is_facet`, `TagRepository._facets_by_tag`) and nothing else — no worker, no search facet, nothing on the public surface |
| readers of `archive_tag_facets.value` ("the canonical spelling the curator chose") | **none**; every select takes `facet_type` only |
| how a place or a producer already reaches a description | the entity axis: **240 `LOC`, 165 `PER`, 57 `ORG`**, **754** document links, with a type the `entity_type` search facet and the public projection both use |
| how `ArchiveDocument.producers` is fed | the staging transfer (`worker_archive_transfer`), from the source's `Produtor` field — **never** from a tag |

And the routing the table was meant to persist already exists as a pure function: the guard's five
signals (`PLACEHOLDER`, `YEAR`, `MEASURE` — properties of the language; `STREET`, `PERSON` — properties
of the collection) plus `is_place_term`. Two writes, one statement each, disagreed about a term that is
both: issue #83 (`PATCH /tags/{id}` files a tag in a drawer while `POST /tags/subject-exclusions` marks
the same term not-a-subject, and no state chip can express the row) and issue #84 ("not a subject" and a
banned spelling are different statements, and the first keeps being undone by the next ingestion).

The population this decides about, measured on the reference collection — 139 rows in
`domain_subject_exclusions`: **75 bare years + 1 placeholder** (garbage), **62 street spellings + 1
person name** (the shape of an entity), of which 113 match an existing tag and only 26 are also banned.
Of the 62 streets, **45 already have an entity with the same spelling** (44 `LOC`) and the person is a
`PER`; **17 have no entity at all**. The routing, not the tag axis, is where those differences belong.

## Decision

### 1. A tag is a subject; the other two destinations live on the axes that own them

The state of a tag is one of **a drawer**, **not a subject**, **nobody decided yet**, plus the
`LOW_CONFIDENCE` view of that last one. `TagCatalogState.FACET` is removed, and with it the state that
existed only to distinguish "not a subject, but a place or a producer" from "not a subject, goes
nowhere".

A term that is a place, a producer or a person belongs to the entity axis — where it carries a type
(`LOC`, `PER`, `ORG`) that search and diffusion actually consume — and a spelling that is both a tag and
an entity is settled by the tag × entity conflict resolution, which already bans the losing spelling and
keeps a ledger. A term that is neither a tag nor an entity (a bare year, a placeholder, a measure) is
garbage, and the guard already refuses it.

### 2. "Not a subject" is a routing decision, and the write bans the spelling

Confirming a term as not-a-subject now also bans the spelling at `TAG` scope, so the next ingestion does
not recreate it. This is the coupling issue #84 asked for, and the measurement that unblocked it is
structural: **the NER never reads tags**. It reads document columns
(`worker_ner.pending_conditions` over `ArchiveDocument`, then `composed_text_sql`), and its blacklist is
`DomainStopwords` with scope `ENTITY`/`ALL` ∪ `DomainNerExclusion` (`load_entity_blacklist`). A
`TAG`-scoped ban — the scope `apply_conflict_resolution` already writes when the entity wins — therefore
silences the subject axis and leaves the NER free. Tags are born from the harvest's indexing points
(`TagService.extract_and_clean_tags` over `indexing_points`), not from the NER; the two axes never read
each other, which is why a term can be both and why the conflict scan exists.

The ban **deletes nothing**: the purge stays a deliberate act behind its preview and its ledger
(#36/#95). The screen names the destination it infers from the guard's signal, and the archivist decides
about the terms with no signal (`pessoas`, `vista aérea`).

### 3. The exclusion refuses a term whose tag is in a drawer (issue #83, option C)

`TagService.exclude_terms_from_subjects` separates the terms it can apply from the ones whose tag is
already filed, and the route reports the blocked ones with their tag and drawer. A term whose tag
already sits in a drawer is a subject question already answered; asking for the opposite is done on the
tag catalogue, where the write is about the tag. Neither write destroys the other's verdict, and the
read has no fourth state in which to express the contradiction.

### 4. The ban is exact, and it never narrows

Two writes plant the same ban — the exclusion and the conflict resolution — so the undo has to know
which one did it:

- `TagRepository.ensure_tag_ban` **widens** the scope (`ENTITY` → `ALL`) and never narrows it. The
  existing `save_stopwords` is an upsert that *moves* the scope, so calling it with `TAG` on a term
  already banned `ENTITY` would silently un-veto the NER.
- `domain_stopwords` gains a **`source`** column (`HUMAN`, `CONFLICT`, `EXCLUSION`), preserved on
  conflict, so the purge preview can say which terms were banned with the archive in mind rather than
  typed by hand. The migration backfills by evidence: a term named by a `ban_created=true` row of
  `archive_conflict_resolution_log` is `CONFLICT`, the rest is `HUMAN`.
- `domain_subject_exclusions` gains **`ban_created`**, mirroring the conflict ledger, and
  `DELETE /tags/subject-exclusions` lifts the ban **only when the exclusion planted it** — the same rule
  `undo_conflict_resolution` already uses.

### 5. `archive_tag_facets` is dropped

A migration drops the table, the `TagFacetType` enum, `TagCatalogState.FACET`, `subject_is_facet()`, the
repository methods, the two routes and the SPA chip in the same change. The single legacy row (one in
`memoriacuritibana`) was read before the drop and is recorded here, so that dropping the table does not
erase the record that a decision was taken: `tag_id = 4144` (`ippuc`),
`facet_type = INSTITUTION`, `value = ippuc`, declared by `Admin` on 2026-10-12 — an experiment no reader
ever consumed.

## Rationale

**Why not keep the facet.** It is a third, parallel statement about something the entity axis already
states with a type; it was consumed by nothing; its `value` column was written and never read; and its
own reader was the state chip whose ambiguity issues #83 and #84 are about. Keeping it would preserve a
distinction whose only consumer is the confusion.

**Why C and not A or B.** A (the exclusion clears the drawer) destroys the human verdict stored in
`macro_category_id` with a write about a term — the direction principle VII forbids. B (the read stops
calling an excluded tag with a drawer "not a subject") leaves the promise on `/assuntos/excecoes` false
for exactly the tags the axis was built for, hiding the contradiction instead of resolving it. D has no
room: `archive_tags.name` is unique and `lower(btrim(name))` is unique, so a term maps to at most one
tag. C is the only option that destroys nothing and tells the truth.

**Why couple the two writes.** Measured on the reference collection, 113 of the 139 excluded terms match
an existing tag and only 26 are banned: without the coupling, every confirmation on
`/assuntos/excecoes` keeps being recreated by the next ingestion, enters the queue and is silenced
again — pending forever, not decided. The counter-argument this issue raised ("the destructive path
inherits terms nobody banned deliberately") no longer holds: the ban is not destructive, and the purge
that is has had a preview and a ledger since #36/#95, which is where the inherited terms are listed.

**Why the scope is the safety.** `word_scope` exists precisely so a statement about the subject axis
cannot blind the extraction axis. A coupling that wrote `ENTITY` or `ALL` would trade a classifier
defect for a silent loss of entities.

## Consequences

**What changes.** The tag catalogue's partition loses a state; two routes disappear from the contract
and `bun run contract` regenerates both halves; `POST /tags/subject-exclusions` gains a preview and a
`blocked` list; the exclusions screen, the Stopwords tab and the Similaridade bar have to say the same
thing; `guides/curate.md` and `curate.pt.md` gain the routing and the ban.

**What the archivist gains.** A "not a subject" that stays decided, a route that refuses the
contradiction instead of storing it, and a purge preview that separates a term banned with the archive in
mind from one typed by hand.

**The accepted cost.** The ban now removes the term from the public record once purged, because a tag is
public (`PublicTagSummary`). For the terms whose signal is `STREET`/`PERSON` and whose entity exists,
nothing is lost. For the **17 measured streets with no entity**, the screen says so, and the archivist
either creates the entity or lets the purge delete the tag; the purge preview is where the death is
listed, as principle VI requires.

## Alternatives considered

- **Keep `ArchiveTagFacet` and make the state chips agree anyway.** Rejected: it resolves the read and
  leaves the write asymmetric, which is the defect — and it keeps a table whose only consumer is the
  ambiguity.
- **Give the facet a consumer** (a public "place" facet, a search dimension). Rejected as a reason to
  keep it: today's place/producer is an entity with a type, and a second source for the same fact is
  principle IV's defect. If a place dimension is wanted, it is built on `entity_type`.
- **The exclusion clears the drawer with a preview and a ledger (A).** Rejected, but recorded: it makes
  the two writes agree by letting a statement about a *term* un-file a *tag*. C keeps the same agreement
  without the destruction.
- **Keep the two writes apart and document it (B in #84).** Rejected: measured, it leaves 87 matching
  terms unbanned and the queue refilling.

## Revisit trigger

If the diffusion surface needs a **place** or a **producer** dimension of its own — a facet a visitor
filters by — that dimension is built on the entity axis (`entity_type`, the entity's own catalogue and
its merge ledger), because that is where the type and the links already live. Reopening the tag axis for
it would recreate this ADR's context; it belongs in a new ADR, not in a condition on this one.
