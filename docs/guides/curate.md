---
sources:
  - apps/curator/src/router.tsx
  - apps/curator/src/components/layout/AppShell.tsx
  - apps/curator/src/routes/**
  - apps/curator/src/lib/permissions.ts
  - src/scrinalia/api/controllers/**
  - src/scrinalia/api/schemas/public.py
  - src/scrinalia/api/security.py
  - src/scrinalia/domains/archive/domain/governance.py
  - src/scrinalia/domains/archive/models/enums.py
  - src/scrinalia/domains/archive/services/tag_service.py
  - src/scrinalia/domains/archive/services/entity_service.py
  - src/scrinalia/domains/archive/services/hierarchy_materialisation_service.py
  - src/scrinalia/domains/archive/repository/tag_repo.py
  - src/scrinalia/domains/archive/repository/entity_repo.py
  - src/scrinalia/domains/archive/workers/catalogue.py
  - src/scrinalia/domains/identity/domain/permissions.py
  - packages/api-contract/openapi.json
---

# Curation

This page is for the archivist who works in the curator SPA. It says, screen by screen, **which
decision is taken there, what the click writes, and whether it can be undone** — and it names what
has no way back at all.

The SPA is served by the API itself (one origin, no CORS), and every screen reads and writes through
the client generated from the OpenAPI contract. The screens are declared in
`apps/curator/src/router.tsx` and the navigation in `apps/curator/src/components/layout/AppShell.tsx`.
The menu has **23 entries** because one route is not a menu entry: the description's own dossier,
`/acervo/$descriptionId`, is reached from the list and from the tree. The router therefore declares
24 screens. The menu itself can be collapsed to icons, which is a presentation choice and not a
permission one — *The menu collapses to icons*, below.

Two cross-cutting pages are worth reading with this one: [Data model](data-model.md) for what the
ledgers and the tables mean, and [Installation and deployment](install.md) for the schema, the
accounts and the deployment around the screens.

## The one rule

Every write either has an undo, or it announces that it does not. The merge keeps a ledger; the
purge has a preview and no undo; editing a description keeps the before and after. When a screen has
neither, this page says so in bold.

Read-only work declares no permission: reading is what an authenticated session is. The screens that
decide carry the area they write to, and the API refuses with a 403 and a sentence when the account
does not carry it.

## What has no way back

!!! warning "These writes have no undo"

    The operations below delete or dissolve a row that nothing else rebuilds. The stopwords purge
    shows a preview; the deletion asks you to type the reference code; the entity merge has neither
    — its panel warns instead. Read the confirmation.

- **Stopwords purge** — `POST /api/v1/taxonomy/tags/stopwords/purge`. Deletes every tag whose name
  is a banned term on the `TAG` or `ALL` axis. The links cascade and the tag's classification goes
  with it. It has a preview (`POST /api/v1/taxonomy/tags/stopwords/purge/preview`, which lists the
  tags that would die) and **no undo**: the merge keeps the previous state and restores it, the
  purge does not. Banning (`POST /api/v1/taxonomy/tags/stopwords`) deletes nothing; only the purge
  does, and the success message says it does not appear in the merge ledger.

- **Excluding a description** — `DELETE /api/v1/documents/{description_id}`. Definitive. The API
  writes an ISAD(G) snapshot of the whole row into the deletion ledger first, and that snapshot is a
  **trail, not a bin**: `/acervo/excluidas` shows it and nothing restores it. The revision ledger
  does not survive (it cascades with the description), which is why the snapshot exists. A
  description with children cannot be excluded — the service refuses and says how many are below;
  exclude or move the children first. The screen asks the archivist to type the reference code (or
  the id, when there is no code) before the button unlocks.

- **Unifying entities** — `POST /api/v1/taxonomy/entities/merge`. The absorbed entities stop
  existing, their links move to the canonical one, and their spellings become synonyms so the
  extractor keeps recognising them. Entities have **no proposal catalogue and no ledger**, so this
  is the one merge with no undo — the tags' privilege is a ledger. The panel warns instead of
  offering a button back, and there is no preview route: the screen states the documented effect
  rather than inventing numbers. Renaming the canonical is part of the same write, and the old name
  becomes a synonym.

- **Deleting or purging entities without links** — `DELETE /api/v1/taxonomy/entities/{entity_id}`
  and `POST /api/v1/taxonomy/entities/orphans/purge`. The screen offers the delete only on a row
  whose use count is zero, and the purge removes every entity no description carries, so no link is
  lost — but the row is gone and there is no ledger to restore it.

There is also one write whose effect reaches backwards: **an NER veto** (`POST
/api/v1/taxonomy/entities/ner-exclusions`) purges the entities already extracted from that spelling,
with their links. Removing the veto (`DELETE`, the screen's "remover veto") re-opens the term for
future extractions; it **does not bring back** what the veto already deleted.

### The batch that does have an undo

Materialising the arrangement from the plan (`POST /api/v1/hierarchy/materialisation/apply`) is
reversible, and the reversal is on the screen. It runs only after a preview
(`POST /api/v1/hierarchy/materialisation/preview`, computed by the same planner) and writes a ledger
entry per run (`GET /api/v1/hierarchy/materialisation/log`). The undo is
`DELETE /api/v1/hierarchy/materialisation/log/{materialisation_id}`, and it restores exactly what the
run changed:

- every description it moved goes back to the **parent and level it had before**;
- the nodes the run **created** are deleted — made possible by restoring first, because the
  self-reference is `RESTRICT`;
- the plans that pointed at a deleted node go back to "not materialised", so the next apply does not
  attach descriptions to a row that no longer exists.

The undo **refuses** when a later run attached descriptions the ledger does not know about, because
reversing then would silently detach work that was never part of this decision. Reversing a finished
run is a new, recorded fact: the entry keeps `undone_at` and who did it.

## Review, diffusion and what the AI may not rewrite

### The review lifecycle

`review_status` is the lifecycle of the human validation over the AI's work. The five values are
`PENDING_AI`, `AI_APPROVED`, `NEEDS_REVIEW`, `HUMAN_APPROVED` and `REJECTED`. `HUMAN_APPROVED` is
the shield: the AI pipeline's write predicate excludes it, so no report worker silently rewrites a
description the archivist validated. Editing any ISAD(G) field, or the description's tags and
entities, sets `HUMAN_APPROVED` through `PATCH /api/v1/documents/{description_id}` (or the link
routes), records the before and after in `archive_document_revisions`, and takes the description out
of the AI's queue.

### The two documented exceptions

- **`worker_embedding`** deliberately does not use the AI write predicate. The embedding is a derived
  index of the text, not archival content: a `HUMAN_APPROVED` description whose text changed must be
  re-embedded, or semantic search would serve a stale vector. It writes only the `embedding` column
  and its own stamp (the MD5 of the effective text), and it skips `REJECTED` descriptions.
- **Publishing is not a lock.** `is_published` is chosen through the same `PATCH` as any ISAD(G)
  field, and it does **not** freeze the description against the AI. The write predicate reads
  `review_status` only. Reusing the review status for diffusion would have made a typo fix equivalent
  to publishing, and would have locked every published description against AI improvement.

The other AI workers are excluded from a `HUMAN_APPROVED` description; what a human decided is not
rewritten by the pipeline.

### Diffusion is not review

Review is a claim about the record; publication is a decision about what to expose.
`is_published` is its own column, edited with the "Publicar na difusão" checkbox on the dossier's
`Descrição` tab, and the public predicate is exactly `is_published`. Nothing is published by default,
so the diffusion surface is born empty.

Publishing exposes the description through the open, unauthenticated surface:

- `GET /api/v1/public/documents` and `GET /api/v1/public/documents/{description_id}`.

Two rules hold there. The `published_only` filter is set **server-side** and is not a client
parameter, so no query string can ask for an unpublished record; and an unpublished id answers 404,
never 403, because a distinct status would confirm that the description exists.

The public projection is narrower than the curator's, field by field. It carries the ISAD(G) fields
`original_title`, `final_title`, `document_date`, `reference_code`, `level`, `scope_content`,
`language_name` and `producers`; the enrichment `typology`, the tags (name), the entities (name and
type) and the subject drawers (name and count); the thumbnail; the branch (`ancestors`) and the
`children_count`. It deliberately does **not** carry the curation process or the unpublished
narrative: `review_status`, `is_anomaly`, `anomaly_reasons`, `archivist_notes`, `provenance`,
`suggested_final_title`, `admin_bio_history`, `admin_archival_history` and `access_conditions`. The
public facet set is also narrower — `anomaly_reason` is not published.

## Who may decide what

Authorization is a declared level per operation, enforced by one guard. The four write permissions
are areas, not buttons:

| Permission | The area |
| --- | --- |
| `CURATE` | the record and its subjects: the ISAD(G) fields, links, tags, entities, conflicts and the taxonomies that move them |
| `CATALOGUE` | the closed catalogues: levels, typologies, collection vocabulary, subject drawers, cleaning rules and text excerpts |
| `OPERATE` | the AI workers: running one, changing its persisted default, and the health panel |
| `ADMIN` | accounts and sessions |

| Role | Carries | Reads |
| --- | --- | --- |
| `VIEWER` | nothing | everything an authenticated session reaches |
| `CURATOR` | `CURATE`, `CATALOGUE` | the same, plus the screens that decide the record and the catalogues |
| `ADMIN` | `CURATE`, `CATALOGUE`, `OPERATE`, `ADMIN` | everything, including the workers and the accounts |

Reading is not a permission: it is what an authenticated session is, and a pure read declares
nothing.

### The menu hides; it never grants

The shell filters its entries by the area the screen **writes** (`apps/curator/src/lib/permissions.ts`,
a mirror of the server's role map), and an empty group is not rendered at all. The screens that only
read carry no permission and stay visible to every role: Início, the collection list, the tree, the
exclusions trail and the arrangement diagnostics. A `VIEWER` therefore sees the "Curadoria" and
"Acervo" groups and, under "Arranjo", only "Diagnóstico" — every other group exists to decide, and
is hidden.

The mirror is one-way on purpose. It can make the menu shorter; it can never make the API accept a
request. A direct URL to a screen the account cannot work in still reaches the API, and the API
answers 403 with a sentence — that is the truth, and the hidden entry is a courtesy.

### The menu collapses to icons

A control in the menu's own header folds it into a 64px column of icons and back, and the browser
remembers the choice: how wide a column of the screen is is presentation state, so it lives in
`localStorage` and not in the account — the API has no column for it.

Collapsed, every entry keeps its icon; the label stays the link's accessible name and the `title`
carries label and hint, so the hint is hidden and never truncated. The active entry keeps the accent
colour, the section headings become hairlines, and the session footer folds into the account's
initial plus two icon buttons. The wordmark leaves the menu but not the page: the attribution renders
at the foot of every screen (`AttributionFooter`, ADR 0006). The icons come from `lucide-react`, one
glyph per entry.

## Curadoria

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Início — `/` | which pending queue to open | yes (read only) |

### Início — `/`

The work list. It answers "what needs me today?" with one card per queue and the route that resolves
it, already filtered. It is a **read view of existing predicates** (`GET /api/v1/curation/inbox`):
nothing is written. A card the shell does not recognise as openable shows "tela pendente" instead of
linking.

## Acervo

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Lista e busca — `/acervo/lista` | how to slice the collection | yes (read only) |
| Árvore — `/acervo/arvore` | where a description sits in the arrangement | yes, by moving it; removing the node means excluding the description |
| Excluídas — `/acervo/excluidas` | none (the ledger of what left) | yes (read only) |
| Descrição — `/acervo/$descriptionId` | the record, its subjects and its place | mostly yes; the exclusion does not |

### Lista e busca — `/acervo/lista`

The faceted search over the collection: the term (lexical or semantic), typology, subject drawer,
entity type, level, a branch of the arrangement and a date range. The URL is the state, so a filtered
list is shareable and the back button works. Nothing is written. The semantic mode carries an honest
note: its measured quality is weak (Hit@10 0.625), so prefer lexical when the term is known.

### Árvore — `/acervo/arvore`

The arrangement as navigation. Selecting a node shows its branch, its children and the descriptions
inside it, all read-only. The screen's one write is "Criar nó" (`POST /api/v1/hierarchy/nodes`,
`CURATE`): it declares a Fundo, Seção or Série that the origin never delivered and that the slicer
therefore cannot propose. The new description is born `HUMAN_APPROVED`, and the level ladder is
validated against the chosen parent by the same rule a move uses. Its placement is reversible by
moving the description; removing the node means excluding the description, which is definitive.

!!! note "Arranjo is not assunto"

    This is the objective axis — where a description sits in the provenance. The subject badges live
    in the list and in the dossier; mixing them here would teach the archivist to "fix" a subject by
    dragging a description into another branch.

### Excluídas — `/acervo/excluidas`

The trail of the deletions, read-only (`GET /api/v1/documents/deletions`), with a server-side search
and pagination because the trail has no ceiling. It is **not a recycle bin**: each entry is the
ISAD(G) snapshot the API wrote before deleting, and nothing here restores anything. It answers "did I
delete this?" — code, title, level, who excluded it, when, how many children it had, and the whole
snapshot on demand.

### Descrição — `/acervo/$descriptionId`

The dossier, with four tabs in the URL. The suggested title is shown **next to** the field it
proposes and is never the stored value: it is derived on read from the `TITLE`-scoped excerpts, and
only the archivist writes `final_title`.

#### Descrição

The decision is the record itself: any ISAD(G) field, the level, the typology, `access_conditions`
and `is_published`, with a note on why. The write is `PATCH /api/v1/documents/{description_id}`
(`CURATE`). It records the before and after of what changed in `archive_document_revisions`, writes
the author from the session, and sets `HUMAN_APPROVED` — which takes the description out of the AI's
queue. Reversible: another edit records a new revision; the history is append-only and the earlier
value is visible in the `Histórico` tab. Publishing and withdrawing use the same command and are
equally reversible.

#### Assuntos

The decision is which tags and entities this description carries, and which drawer each tag belongs
to. The writes are `POST`/`DELETE /api/v1/documents/{description_id}/tags[/{tag_id}]` and the entity
pair (`CURATE`), plus `PATCH /api/v1/taxonomy/tags/{tag_id}` for the drawer. Linking and unlinking
are reversible: the revision stores the **whole list of names** on each side, and calling the same
route twice writes no revision.

!!! warning "The drawer is a decision about the vocabulary, not about this description"

    Changing a tag's drawer moves it for **every** description that carries the tag, and the screen
    says so next to the select. Choosing "sem gaveta" gives the tag back to the AI classifier, which
    will try to file it again on the next run.

#### Arranjo

The decision is where this description sits and at which level. The write is
`POST /api/v1/hierarchy/nodes/{description_id}/move` (`CURATE`), and the route states where the node
goes: `new_parent_id=null` means "to the root", so there is no way to change only the level — the
screen always sends the parent it is showing. The API validates before writing (an Item cannot have
children, a Dossiê cannot be left without a parent, moving into its own subtree is refused), and
moving a unit takes the whole subtree: the path is rewritten in one statement. The change is recorded
in this description's history and is reversible by moving the unit back.

#### Histórico

The revisions of this description, read-only, field by field with the old and the new value. At the
end of the history sits the exclusion, away from the page header on purpose — it is the one action
that removes a record for good, and the confirmation (type the reference code) is what separates
"excluir" from "excluir *esta* descrição". See **what has no way back** above.

## Arranjo

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Plano de arranjo — `/arranjo/plano` | approve or reject each proposed rung, and materialise the tree | yes — a decision can be reopened, and the materialisation has an undo |
| Diagnóstico — `/arranjo/diagnostico` | none (the evidence; the fix is elsewhere) | yes (read only) |

### Plano de arranjo — `/arranjo/plano`

The machine reads the reference codes and proposes the rungs; the decision is the archivist's. For
each rung the evidence comes first — the document count, the declared levels, the samples — and the
form last:

- **Propor níveis** — `POST /api/v1/hierarchy/plans/suggest` (`CURATE`). It writes the questions. It
  is idempotent by code and never rewrites a rung that left `SUGGESTED`, so the same question is not
  asked again.
- **Aprovar** a rung — `PATCH /api/v1/hierarchy/plans/{plan_id}` (`CURATE`) with `APPROVED`, the
  chosen level, an optional title, an optional "fundir em" code and a note. Approving **requires**
  the level: it is the decision the code cannot take.
- **Rejeitar** — the same route with `REJECTED`. A rejected rung leaves its descriptions orphan on
  purpose: they fall to the nearest approved rung above.
- **Reabrir decisão** — the same route with `SUGGESTED`. Reversible: the decision returns to the
  queue and the next proposal may refresh its evidence. The decision is never overwritten by a new
  proposal.

The side panel materialises the tree: it always offers "Conferir o que será feito" first, and the
apply button stays disabled until the preview exists. Only approved rungs are materialised. The
preview and the apply share one planner, so the approved number is the written number. What the undo
restores is described under **the batch that does have an undo**.

### Diagnóstico — `/arranjo/diagnostico`

The structural diagnosis, one section per issue, each with its count and its evidence (a section with
zero stays visible, because knowing the check ran matters). It offers **no silent correction**: every
row links to the screen where the fix is a recorded decision — the plan, the tree, or the
description's arrangement tab. The counts overlap deliberately (a Dossiê at the root is both `ORPHAN`
and `DOSSIER_WITHOUT_PARENT`), so there is no grand total.

## Catálogos

The two closed catalogues the archivist maintains and the collection vocabulary. None of them
deletes: a row retires with `is_active=false`, because the foreign keys are `SET NULL` and removing a
row would unclassify every description pointing at it while erasing the fact that it ever existed.

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Níveis de descrição — `/arranjo/niveis` | the ladder the arrangement is written against | yes (retire and reactivate) |
| Tipologias — `/arranjo/tipologias` | the diplomatic form the classifier proposes | yes (retire and reactivate) |
| Vocabulário do acervo — `/vocabulario` | what this collection's codes and terms mean | yes (retire and reactivate) |

### Níveis de descrição — `/arranjo/niveis`

The catalogue of levels. Creating a rung is `POST /api/v1/hierarchy/levels` and editing one is
`PATCH /api/v1/hierarchy/levels/{level_id}` (`CATALOGUE`): name, description, accepted spellings,
whether it requires a parent and whether it allows children. Two rules the screen states rather than
works around:

- **there is no delete.** `is_active=false` is the way out, and the weight of a retired rung stays
  visible;
- **the ordinal is not editable.** Changing it would renumber the tree the past was decided against;
  a wrong ordinal is a new rung, not a rename.

The asymmetry is deliberate: an unknown level arriving from the origin enters as unclassified and
the description carries on, while the archivist cannot store a level that does not exist.

### Tipologias — `/arranjo/tipologias`

The catalogue of documental typologies — the diplomatic form (ata, ofício, planta), neither
arrangement nor subject. `POST /api/v1/typologies` and `PATCH /api/v1/typologies/{typology_id}`
(`CATALOGUE`) maintain the name and the context description. The classifier receives **only the
name**: appending the context makes the model lose the entailment and collapse the collection onto
one typology (measured), so the context is documentation for the reader. Retiring a typology is the
only lever that reaches the model — it stops being proposed without a single classified description
being touched, which is why the weight of the retired ones stays on screen.

### Vocabulário do acervo — `/vocabulario`

What *this* collection declares, as opposed to what the language or the software fixes. Two lists:

- **arrangement names** — `POST`/`PATCH /api/v1/vocabulary/arrangement-terms` (`CATALOGUE`): a token
  (`SMU`) or a whole code (`BR PRADAP`) mapped to the name the arrangement proposal suggests; the
  whole code wins over the last token;
- **collection terms** — `POST`/`PATCH /api/v1/vocabulary/collection-terms` (`CATALOGUE`): the
  spellings the collection carries and that are not subjects, typed so the PLACE facet can claim a
  place while a person's name goes nowhere.

What belongs to the Portuguese language itself — *rua*, *não identificado*, *303 anos*, a bare year
— lives in the language profile and does **not** appear here: changing it would change the meaning
the software gives to a word. Withdrawing a term does not delete it, and a withdrawn term is treated
as a subject again on the next classifier run.

## Assuntos

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Tags — `/assuntos/tags` | the weight, the duplicates, the merge queue and the banned terms | the merge yes (ledger); the purge **no** |
| Categorias — `/assuntos/categorias` | the subject drawers the classifier reads | yes (retire and reactivate) |
| Descobrir gavetas — `/assuntos/descobrir` | whether a proposed theme deserves a drawer | yes (the proposal writes nothing) |
| Não é assunto — `/assuntos/excecoes` | which terms leave the subject axis | yes (banning deletes nothing) |

### Tags — `/assuntos/tags`

One route, four questions, one conversation: the archivist sees that `alvenarias` weighs little,
finds its near-duplicate and decides whether to absorb it. The active tab is in the URL.

#### Relevância

Read-only: `GET /api/v1/taxonomy/tags/relevance/{method}`. The count shows what dominates the
collection; TF-IDF shows what is specific, punishing what appears everywhere. The two lists answer
different questions on purpose.

#### Similaridade

Pairs by trigram similarity, shown raw with the similarity score and both ids. The read is
`GET /api/v1/taxonomy/tags/similar`. The similarity does not say which spelling is the good one:
`'alameda cabral'` and `'al. alameda cabral'` score 1.000.

The decision is to unify: `POST /api/v1/taxonomy/tags/merge` (`CURATE`), after a dry run
(`POST /api/v1/taxonomy/tags/merge/preview`, a read that computes the same plan the write executes).
The panel always opens with the impact first: documents updated, links rewritten, tags absorbed,
spellings registered and repointed, and the one warning that must be read before the click —
`category_would_be_lost`, when the canonical has no drawer and an absorbed tag does, so the merge
would erase a subject classification.

The merge is **reversible**: the write is logged per absorbed tag in the merge ledger before
anything changes, and the undo (`DELETE /api/v1/taxonomy/tags/merge-log/{merge_id}`, `CURATE`)
restores the row, the links, the classification and the spelling state. The undo deletes only the
links the merge created, so it cannot detach a document that already carried the canonical. Rows can
also be marked across lines and unified as a cluster, which is how one merge spans several pairs
(`carlos de carvalho` appears in more than one row).

#### Propostas de merge

The machine's clusters, with the decision kept apart from the write:

- **Propor clusters** — `POST /api/v1/taxonomy/tags/merge-proposals/suggest` (`CURATE`) registers
  the question. A verdict already taken is never overwritten.
- **Conferir impacto** — `POST /api/v1/taxonomy/tags/merge/preview` with the proposal id, the same
  planner.
- **Aprovar** / **Rejeitar** — `PATCH /api/v1/taxonomy/tags/merge-proposals/{proposal_id}`
  (`CURATE`). Approving records the **intent**; it does not absorb anything. The status goes
  `SUGGESTED` → `APPROVED`/`REJECTED` → `APPLIED`.
- **Aplicar em lote** — `POST /api/v1/taxonomy/tags/merge/batch` (`CURATE`) absorbs the selected
  clusters and writes `APPLIED` in the same savepoint. The screen refuses a batch over 200 clusters
  (the API refuses it too). A cluster whose members already left is reported as `skipped`, never as
  a failure.
- **Editar** a cluster — marks the tags that do not belong out of the set, chooses the canonical and
  applies the revised selection through the same planner; the machine's proposal is then closed as
  rejected, because the question was answered another way.

The **ledger** below lists only applied merges, each with the absorbed name, the canonical, the
document count, the author and the time. Its undo is the exact restoration described above, and the
screen's "desfazer" is the same route. A merge made here also works through a proposal, so the
ledger is the write's history and the status is the decision's.

#### Stopwords

The banned terms, and the one destructive write in the taxonomy. The screen keeps three things
apart:

- **Banir** — `POST /api/v1/taxonomy/tags/stopwords` (`CURATE`) records that a term is not worth
  considering on one axis: `TAG` (the subject axis), `ENTITY` (NER) or `ALL`. A word has exactly one
  scope — re-banning it **moves** it — and banning **deletes nothing**.
- **Desbanir** — `DELETE /api/v1/taxonomy/tags/stopwords` (`CURATE`). Reversible.
- **Purgar** — `POST /api/v1/taxonomy/tags/stopwords/purge` (`CURATE`), after
  `POST /api/v1/taxonomy/tags/stopwords/purge/preview`. This is the write that deletes the tags, and
  it has **no undo**. The preview lists the tags that would die, with their document count and
  drawer, and the apply button is disabled until the preview exists.

!!! warning "The scope protects the other axis"

    The purge reads only `TAG`/`ALL`. A term banned on the `ENTITY` axis is a NER veto and can never
    make the subject purge delete a tag the curator kept — the two are stored in different places on
    purpose.

### Categorias — `/assuntos/categorias`

The drawers the subject classifier reads. `POST /api/v1/taxonomy/macro-categories` and
`PATCH /api/v1/taxonomy/macro-categories/{category_id}` (`CATALOGUE`) create, rename, describe,
retire and reactivate them; a retired drawer keeps its weight visible. Two honest notes the screen
gives: the **classifier label** is a curator override, not an improvement — measured on 44
hand-labelled tags, a phrase instead of a bare name scores 0.000 with 65% of the tags in one drawer
— and a **new drawer only takes effect when the classifier runs again**, because the worker's stamp
is the hash of the label set, which returns the tags to the queue on its own.

### Descobrir gavetas — `/assuntos/descobrir`

Runs the real clustering engine (`POST /api/v1/taxonomy/tags/suggest-macro`, read-only:
`AUTHENTICATED`) over the tags or the documents to find a theme the vocabulary does not cover yet. It
is a deliberate click and not a page load: the engine takes seconds and may run in a subprocess. The
clusters are **proposals** — nothing enters the vocabulary until the archivist registers it, which is
`POST /api/v1/taxonomy/macro-categories` (`CATALOGUE`). Discarding a proposal is local to the screen.
A corpus too small answers an empty suggestion with a message, not an error.

### Não é assunto — `/assuntos/excecoes`

The curated half of "this is not a subject at all". The deterministic guard catches what has a shape
— a date, a placeholder, a street name, a bare number — and on the real measurement it caught 1 of 4
of the hand-labelled non-subjects; the rest are semantic calls no rule resolves (`pessoas`,
`vista aérea`, `capanema`). The screen shows the guard's candidates with their evidence (weight,
whether the PLACE facet claims the term, whether the same spelling is also an entity), and offers to
register them with `source=RULE` or one at a time.

The write is `POST /api/v1/taxonomy/tags/subject-exclusions` (`CURATE`) and the reversal is
`DELETE` (`CURATE`, the screen's "restaurar"). **Banning here deletes nothing**: the tag stays in the
collection, stays linked and stays reachable by search — only the subject classification stops
guessing at it. The route deliberately proposes nothing for the semantic half: the available signals
lie, and a model that does not know how to abstain would answer confidently and wrongly.

## Entidades

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Entidades — `/entidades/lista` | the type of a name, and whether two names are one | the type yes; the merge **no** |
| Exclusões de NER — `/entidades/excecoes` | which spellings are subjects, not proper names | the veto row yes; the entities it purged **no** |
| Conflitos — `/entidades/conflitos` | whether a collision belongs to the subject axis or to the names | yes (ledger and undo) |

### Entidades — `/entidades/lista`

The named-entity vocabulary, by weight or by similarity. Three decisions:

- **Reclassify the type** — `PATCH /api/v1/taxonomy/entities/{entity_id}/reclassify` (`CURATE`),
  only between `ORG`, `PER` and `LOC`. This is not renaming a label: the service also writes the
  anchoring synonym, so the extractor returns that spelling with the new type in every future run.
- **Excluir** an entity — `DELETE /api/v1/taxonomy/entities/{entity_id}` (`CURATE`), offered only on
  a row no description carries, where deleting loses no link. No undo.
- **Purgar órfãs** — `POST /api/v1/taxonomy/entities/orphans/purge` (`CURATE`): the same decision in
  batch. No undo.
- **Unificar** — `POST /api/v1/taxonomy/entities/merge` (`CURATE`): the absorbed entities stop
  existing, their links move to the canonical, their spellings become synonyms, and an optional new
  name for the canonical makes the old one a synonym too. Entities have no proposal catalogue and
  **no ledger**: there is no undo, and the panel says so instead of offering a button back. There is
  no preview route either — the screen states the documented effect rather than inventing numbers.
  The pair list is raw evidence, with both ids, because two rows can read the same name and the
  canonical is a choice the archivist has to be able to tell apart.

### Exclusões de NER — `/entidades/excecoes`

The veto "this spelling is a subject, not a proper name". The write is `POST
/api/v1/taxonomy/entities/ner-exclusions` (`CURATE`), with a reason kept for audit; the reversal is
`DELETE` (the screen's "remover veto"). Two behaviours the screen states because neither is visible
in the list: the block is **by token boundary**, not by exact name (spaCy merges neighbouring tokens,
so a banned `iptu` would not stop `"IPTU do Batel"` under an exact comparison), and it **applies to
the past** — the entities already extracted from that spelling are deleted, with their links, and
removing the veto does not bring them back.

This is the other half of the bidirectional governance: it records the curator or the judge saying
"this belongs to the subject axis", and it is stored apart from the subject-axis stopwords on
purpose, so a veto here can never make the subject purge delete a tag the curator kept.

### Conflitos — `/entidades/conflitos`

The same spelling on both axes: "is this a subject or a proper name?". Three reads answer three
questions, and reading only the first is what used to hide the judge's work:

- **Pendentes** — the live trigram scan (`GET /api/v1/taxonomy/conflicts/cross-domain`), annotated
  with the judge's verdict where there is one and separated by `pair_kind`: "grafias diferentes" (a
  spelling question) and "nomes idênticos" (a structural question) are not the same list, and mixed
  together neither is visible.
- **Decididos pelo juiz** — the review queue (`GET /api/v1/taxonomy/conflicts/judged`). An
  auto-resolution deletes the losing row, so most of the judge's decisions cannot appear in the live
  scan at all.
- **Resoluções** — the ledger (`GET /api/v1/taxonomy/conflicts/resolutions`), with the undo.

The decision is preceded by the preview (`POST /api/v1/taxonomy/conflicts/resolve/preview`, a read):
it returns **both verdicts** with what each one transfers, deletes and blocks, computed by the same
planner the write executes. The two verdicts are stored in **different places on purpose**:

- **the tag wins** — the entity's links move to the tag, the entity row is deleted and the term is
  recorded in `domain_ner_exclusions`, carrying the reason, the source and the tag that justifies it;
- **the entity wins** — the tag's links move to the entity, the tag row is deleted and the tag name
  joins the tag-scoped stopwords.

Collapsing the two would let a NER veto make the subject purge delete the winning tag.

Resolving is `POST /api/v1/taxonomy/conflicts/resolve` (`CURATE`) and the undo is
`DELETE /api/v1/taxonomy/conflicts/resolutions/{resolution_id}` (`CURATE`). The undo is exact
because the ledger records `created_link_ids` and `ban_created`: both writes use
`ON CONFLICT DO NOTHING`, so reversing a later resolution must not lift a ban an earlier one planted,
nor delete a link that predated it. The ledger restores the losing row from its snapshot. A pair
already resolved can be decided again — the second resolution is independent, and each has its own
undo.

!!! note "A resolved pair leaves the live scan"

    The resolution deletes the losing row, so the trigram join cannot return it and the live list has
    nothing to annotate. That is why the work survives in the judge's queue and in the ledger, and
    why the `Decididos` and `Resoluções` tabs exist.

## Qualidade

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Trechos — `/qualidade/trechos` | which consumer stops reading a repeated excerpt | yes (retire or remove from the catalogue) |
| Regras — `/qualidade/regras` | whether a rule rewrites the text or only flags it | yes: deactivating has a route back, and the retired rule stays on the screen |
| Anomalias — `/qualidade/anomalias` | none (the correction is the record's review) | yes (read only) |

### Trechos — `/qualidade/trechos`

The catalogue of repeated excerpts. This is the largest measured gain of the project: 53% of the
collection shared the same `scope_content` block, and a repeated title prefix dominated the
embeddings and degraded the search. The decision that matters is the **scope**: which consumer stops
reading the excerpt — `EMBEDDING` (the vector), `NER` (the names) or `TITLE` (the suggested title).
The same block is dropped from the consumers it damages and kept where it helps: approving
everything the machine suggested worsened the ranking (Hit@10 0.562 → 0.500), which is why there is
no "approve all" button on this screen.

- **Procurar** — `POST /api/v1/quality/text-templates/suggest` (`CATALOGUE`) registers the candidates
  as **inactive suggestions**: nothing enters the AI text before an archivist approves a scope.
- **Escrever um trecho** — `POST /api/v1/quality/text-templates` (`CATALOGUE`). It is born approved
  and applied and returns the affected descriptions to the AI queue; the create button only unlocks
  after the impact is seen.
- **Aprovar / rejeitar / desativar / salvar escopo / remover** —
  `PATCH`/`DELETE /api/v1/quality/text-templates/{template_id}` (`CATALOGUE`). Removing takes the
  excerpt out of the catalogue and returns the affected descriptions to the AI queue.

### Regras — `/qualidade/regras`

The one place a regular expression can rewrite the collection. `rule_kind` is the difference between
cleaning and destroying, and the screen makes the choice explicit:

- `REWRITE` replaces every match in the target column on the next run — the cleaning worker filters
  it explicitly, so a validation rule never rewrites;
- `VALIDATE` and `LLM_CHECK` only flag; the flag becomes an anomaly reason on the description.

The writes are `POST /api/v1/quality/cleaning-rules` (`CATALOGUE`) — saved only after a preview, for
a rule that rewrites — `PATCH /api/v1/quality/cleaning-rules/{rule_id}/deactivate` and
`PATCH /api/v1/quality/cleaning-rules/{rule_id}/activate`, both `CATALOGUE`. A rule is never
deleted, and the way back is a route rather than a new rule: the listing takes
`include_inactive=true`, which is what puts the retired rules at the bottom of the screen with the
button that returns them to the queue. Reactivating keeps the id and the history that re-creating
the rule would have lost. Deactivation is the safe half of the pair — it is what you reach for when
a rule is wrong, so the way out of it has to exist.

An active `REWRITE` rule is the loudest thing on the screen, and the preview is what makes it
visible: a test rule once sat active and stamped the whole collection without matching anything.

### Anomalias — `/qualidade/anomalias`

What the quality validator marked, read-only (`GET /api/v1/documents` filtered to `NEEDS_REVIEW`,
optionally by anomaly reason). The counts by reason are the search's own facet over the whole
filtered set, and clicking one narrows the list. An empty queue has two very different causes and
the screen tells them apart: the collection is clean, or no rule that flags (a `VALIDATE` or
`LLM_CHECK` rule) is active — a `REWRITE` rule changes the text and never flags. The correction is
the human review of the record, in the dossier.

## Sistema

The machine, not the collection. Everything here belongs to whoever operates the installation.

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Workers de IA — `/sistema/workers` | which model a worker runs with, and whether to run it now | the configured default yes; a run's effects follow what it wrote |
| Execuções — `/sistema/execucoes` | none (the ledger and the grouped failures) | yes (read only) |
| Diagnóstico — `/sistema/diagnostico` | none (database, models, storage, process) | yes (read only) |

### Workers de IA — `/sistema/workers`

The catalogue of the nine workers, in pipeline order, with the effective engine, preset and config on
the collapsed row — "with which model is this running?" is the question the screen exists to answer.
Two writes per worker, both `OPERATE`:

- **Rodar agora** — `POST /api/v1/system/workers/{worker_name}/runs`. The run uses the effective
  configuration, adjusted only for this execution; nothing in the panel becomes the default. Every
  run leaves a row in the run ledger, and a worker with a run in flight disables both buttons — the
  guarantee is the partial unique index in the database, and the screen only avoids offering what
  the database would reject.
- **Configurar** — `PUT /api/v1/system/workers/{worker_name}/settings` sets the persisted default
  (partial on purpose: an empty field keeps following the code), and
  `DELETE /api/v1/system/workers/{worker_name}/settings` removes it. Every write leaves a revision
  (`GET /api/v1/system/workers/{worker_name}/settings/revisions`), so the default is reversible: the
  revision list is right there, and "Voltar ao padrão do código" removes the row.

The panel itself offers no undo for a run. The reversibility of a run is the reversibility of what it
wrote — a merge undo, a materialisation undo, a conflict undo — and a worker that stamps its queue
does not redo its work just because it is run again. A worker marked as not respecting the human
review block is `worker_embedding`, the documented exception.

### Execuções — `/sistema/execucoes`

The run ledger, read-only: one row per execution, from the command line and from the panel, carrying
the **resolved** configuration the run used (so it stays readable after a preset changes in code),
the duration, the outcome and who asked. Above it, the failures of the last 30 days grouped by root
cause (`GET /api/v1/system/failures`), which answer the question the ledger cannot: forty rows saying
the same sentence are one cause. Clicking a group filters the ledger below instead of opening a
second list, and a failure's reference is what is searched in the log.

### Diagnóstico — `/sistema/diagnostico`

Four independent probes (`GET /api/v1/system/health`, `OPERATE`): the database with its counts, the
Ollama server with the models the presets require and which of them are missing, the thumbnail
storage, and the effective process configuration. Each probe answers on its own — a database that is
offline must not hide that Ollama is fine — and no secret value is ever shown: the process card
reports that a secret exists, never what it is. Nothing here writes.

## Configurações

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Usuários — `/configuracoes/usuarios` | who exists, what they may do, and where they are signed in | yes (deactivate and reactivate) |

### Usuários — `/configuracoes/usuarios`

The accounts of the installation, the `ADMIN` surface. The writes are `POST /api/v1/users` (create),
`PATCH /api/v1/users/{user_id}` (name, role, active), `POST /api/v1/users/{user_id}/password` (reset)
and the session routes `GET`/`DELETE /api/v1/users/{user_id}/sessions[/{session_id}]` — all `ADMIN`.
Four facts the API enforces and the screen states:

- **the password created here is temporary.** The administrator typed it, so the account replaces it
  at the first sign-in, exactly like the CLI bootstrap;
- **deactivating ends every session of the account immediately**, which is what makes the flag real;
- **resetting the password ends every session** and lifts a lockout caused by failed attempts;
- **the last active administrator cannot be deactivated or demoted** (`LastAdminError`, 409). It is
  the one lockout with no way back through the screen; the way in is the CLI on the host.

There is no delete. An account is deactivated, because the ledgers carry its name and its id, and a
decision whose author no longer exists is a worse record than a closed account. Revoking a session id
that belongs to another account answers 404 and not 200, because the id alone must not enumerate
other people's sign-ins; the row that is the archivist's own session is marked "esta sessão".
