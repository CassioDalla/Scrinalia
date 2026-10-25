---
sources:
  - apps/curator/src/router.tsx
  - apps/curator/src/components/layout/AppShell.tsx
  - apps/curator/src/components/layout/PageHeader.tsx
  - apps/curator/src/components/layout/LoginForm.tsx
  - apps/curator/src/components/layout/PasswordChangeForm.tsx
  - apps/curator/src/routes/**
  - apps/curator/src/lib/permissions.ts
  - apps/curator/src/lib/screens.ts
  - apps/curator/src/lib/copy.ts
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
  - docs/adr/0011-first-run-setup-without-an-open-door.md
---

# Curation

This page is for the archivist who works in the curator SPA. It says, screen by screen, **which
decision is taken there, what the click writes, and whether it can be undone** — and it names what
has no way back at all.

The SPA is served by the API itself (one origin, no CORS), and every screen reads and writes through
the client generated from the OpenAPI contract. The screens are declared in
`apps/curator/src/router.tsx`, and **what each one is called** in
`apps/curator/src/lib/screens.ts`: one record per screen holds the label the menu, the settings card
and the page's own heading all read, so the three cannot disagree (*One name per screen, one verb per
action*, below). The menu has **16 entries**: the screens nobody opens in the middle of cataloguing —
the arrangement plan, the catalogues, the worker panel, the run ledger, the diagnostics and the
accounts — are cards of `/configuracoes` rather than menu entries (*Configurações*, below). One route
is not reached from the menu either: the description's own dossier, `/acervo/$descriptionId`, comes
from the list and from the tree. The router therefore declares **26 screens**. The menu itself can be
collapsed to icons, which is a presentation choice and not a permission one — *The menu collapses to
icons*, below.

Two cross-cutting pages are worth reading with this one: [Data model](data-model.md) for what the
ledgers and the tables mean, and [Installation and deployment](install.md) for the schema, the
accounts and the deployment around the screens.

## The one rule

Every write either has an undo, or it announces that it does not. The merge, the stopwords purge and
the NER purge keep a ledger; editing a description keeps the before and after. When a screen has
neither, this page says so in bold.

Read-only work declares no permission: reading is what an authenticated session is. The screens that
decide carry the area they write to, and the API refuses with a 403 and a sentence when the account
does not carry it.

## What has no way back

!!! warning "These writes have no undo"

    The operations below delete or dissolve a row that nothing else rebuilds. The deletion asks you
    to type the reference code. Read the confirmation.

- **Excluding a description** — `DELETE /api/v1/documents/{description_id}`. Definitive. The API
  writes an ISAD(G) snapshot of the whole row into the deletion ledger first, and that snapshot is a
  **trail, not a bin**: `/acervo/excluidas` shows it and nothing restores it. The revision ledger
  does not survive (it cascades with the description), which is why the snapshot exists. A
  description with children cannot be excluded — the service refuses and says how many are below;
  exclude or move the children first. The screen asks the archivist to type the reference code (or
  the id, when there is no code) before the button unlocks.

- **Deleting or purging entities without links** — `DELETE /api/v1/taxonomy/entities/{entity_id}`
  and `POST /api/v1/taxonomy/entities/orphans/purge`. The screen offers the delete only on a row
  whose use count is zero, and the purge removes every entity no description carries, so no link is
  lost — but the row is gone and there is no ledger to restore it.

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
type) and the subject categories (name and count); the thumbnail; the branch (`ancestors`) and the
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
| `CATALOGUE` | the closed catalogues: levels, typologies, collection vocabulary, subject categories, cleaning rules and text excerpts |
| `OPERATE` | the AI workers: running one, changing its persisted default, and the health panel |
| `ADMIN` | accounts and sessions |

| Role | Carries | Reads |
| --- | --- | --- |
| `VIEWER` | nothing | everything an authenticated session reaches |
| `CURATOR` | `CURATE`, `CATALOGUE` | the same, plus the screens that decide the record and the catalogues |
| `ADMIN` | `CURATE`, `CATALOGUE`, `OPERATE`, `ADMIN` | everything, including the workers and the accounts |

Reading is not a permission: it is what an authenticated session is, and a pure read declares
nothing.

### Signing in, and forgetting the password

The sign-in form is not a route: it renders in the shell's own place, so a deep link survives it — an
archivist who opens `/acervo/lista` while signed out signs in and lands on `/acervo/lista`. A wrong
password and an address that does not exist answer the same sentence, on purpose: the form is not an
enumeration of who has an account.

There is **no e-mail recovery** in this installation, and the screen does not pretend otherwise. Under
the button, *Esqueci minha senha* opens a short explanation of the path that does exist: an
administrator resets the password on the accounts screen (*Usuários*, below), the password is
temporary and the account replaces it at the next sign-in, the reset ends every session of that
account and lifts a lockout — and if the last active administrator is the one who cannot get in, the
host's terminal is the way back ([Operations](operate.md) owns that procedure). Nothing on the screen
promises a message, because no message is sent.

**The temporary password is a credential for the change and nothing else.** While the account still
carries it, the API refuses every operation of `/api/v1` — reads included — with
`PASSWORD_CHANGE_REQUIRED`, and the shell draws the forced password change in the place of every
screen. The three operations that forced screen stands on stay reachable: reading the session
(`GET /auth/me`), ending it (`POST /auth/logout`) and replacing the password (`POST /auth/password`,
which clears the flag). The refusal does not depend on the screen: a script holding the password that
was printed to a terminal, or typed by an administrator, gets the same sentence and no access to the
collection. The change opens the rest of the API in the same session.

### The menu hides; it never grants

The shell filters its entries by the area the screen **writes** (`apps/curator/src/lib/permissions.ts`,
a mirror of the server's role map), and an empty group is not rendered at all. The screens that only
read carry no permission and stay visible to every role: Início, the collection list, the tree, the
exclusions trail and the arrangement diagnostic. A `VIEWER` therefore sees the "Acervo" group and the
"Início" entry, which stands with no heading — every other group exists to decide, and is hidden.

The same rule governs the cards of `/configuracoes`, and it is the card catalogue
(`apps/curator/src/lib/settings.ts`) that both the page and the menu entry read: a card is hidden when
the account does not carry the area its screen writes, a tab whose cards are all hidden is not
rendered, and the entry is in the menu while **at least one** card is reachable. So a `VIEWER` has no
Configurações at all, and a direct URL to it reaches a page that says why it is empty instead of
pretending to be broken.

The mirror is one-way on purpose. It can make the menu shorter; it can never make the API accept a
request. A direct URL to a screen the account cannot work in still reaches the API, and the API
answers 403 with a sentence — that is the truth, and the hidden entry is a courtesy.

### One name per screen, one verb per action

The interface grew screen by screen, and so did its vocabulary: the menu said *Tags* while the page
it opened said "Vocabulário de tags", the settings card said *Usuários* while the page said "Contas",
and two different screens were both called *Diagnóstico*. Two files now own those words.

`apps/curator/src/lib/screens.ts` holds **one record per screen** — its route, the label, and the hint
that says what it decides. The label is the same string in the three places that used to disagree:
the menu entry, the settings card and the page's own `<h1>`, which `PageHeader` resolves from the
screen id a route declares. A route therefore cannot pass a heading of its own; the dossier is the one
exception, and the catalogue is what flags it as the screen whose heading is the record's own title.

Under the heading the header has the same four slots on every screen: the label, one line saying what
the screen decides, the **status** of what was read — a count, a filter, a total — and the actions.
The count used to compete with the explanatory line for the same slot, which is why some screens
explained themselves and others only reported totals; while the read is in flight the status slot
holds a skeleton of its own height, so the header does not jump when the numbers arrive.

`apps/curator/src/lib/copy.ts` holds the product's name — re-exported from `lib/attribution.ts`, which
owns it for the license notice — and **one verb per action**, with the word for it while it runs. The
verbs this page uses are that file's:

| Action | The word on the screen |
| --- | --- |
| writing an edited row | **Salvar** |
| bringing a row into existence | **Criar** (the trigger beside it reads *+ Nova…*) |
| taking a term off a list — a veto, an exclusion | **Remover** |
| destroying a record, always behind a preview or a typed confirmation | **Excluir** |
| the `is_active` switch on a **catalogue row** — a level, a typology, a category, a cleaning rule, a collection term | **Aposentar** / **Reativar** |
| disabling an **account** | **Desativar** / **Reativar** |
| launching one worker run | **Rodar agora** |
| unifying two vocabulary entries | **Mesclar** |
| committing a computed plan | **Aplicar** |
| computing what a destructive write would do, without writing it | **Conferir impacto** |

`Aposentar` and `Desativar` are deliberately two words: a catalogue row and an account leave the
system in different ways, and one word for both would say they do not. Banning a term keeps its own
verb (`Banir` / `Desbanir`), because it is a different flag and it deletes nothing.

### The screen is one window tall

The shell is exactly one viewport and the **page never scrolls**: what scrolls is the content
column, so the rail — and the entry to `Configurações` at its foot — stays where it is on a long
screen. The screen's own header is sticky inside that column, which is what keeps the title, the
status and **the actions** in reach: "Propor níveis", "Rodar agora" and "Excluir órfãs" used to leave
the window with the content. Measured at 1440x900 on the entities list: the document is 900px in a
900px window, the content is 3299px in an 867px column, and the menu is 734px in a 734px box.

The column has **no maximum width**: it fills whatever the window gives it, so the same screen is the
same width on every monitor. Before this, each screen carried its own cap and they had drifted —
`max-w-5xl` on most, `max-w-4xl` on five, `max-w-6xl` on one — so two screens side by side on a wide
display stopped growing at different points. What keeps its own cap is the *content*: a paragraph
keeps a readable measure, a text field keeps a field's width.

The menu **folds into one open section**, plus the section the archivist is standing in — that one is
open by construction, because an active entry hidden inside a collapsed group is a menu that hides
where you are. Clicking a heading opens it and closes the one opened by hand; navigating closes that
one, so the menu never drifts into three. A heading carries no icon: the glyph belongs to the entry.
`Início` stands at the top with no heading, like the landing at the foot, because a section that
gathers one line is a line of chrome.

### The identity is on screen

The rail is the identity's navy (`#14202B`), and the logomark is in it in both states: expanded it is
the full lockup — the card with its terracotta tab, then **Scrinalia** in PT Serif — and collapsed it
is the cropped mark alone. Collapsed, that mark is **also the control that expands the rail**: the
brand is the thing you click to get the words back, which is what makes it worth keeping at 64px.

A 2px terracotta rule closes the screen's header, and the two cards that come before a session —
the sign-in form and the first-run setup — carry the same motif at their top, where the name used to
be plain text. The two are not the same plate: the setup card centres the lockup under the tagline,
and the sign-in card sets a larger lockup to the right and carries no tagline at all — there the
plate is the mark alone.

The accent is still the blue it was, and the terracotta is a **brand** colour and not an interactive
one: the terracotta is `oklch(… 31)` and the danger colour is `oklch(… 25)`, six degrees apart, so a
terracotta button and "Excluir" would have been the same colour. The navy, on the other hand, shares
the accent's hue on purpose — which is why the rail and the buttons look like one thing.

### The menu collapses to icons

A control in the menu's own header folds it into a 64px column of icons and back, and the browser
remembers the choice: how wide a column of the screen is is presentation state, so it lives in
`localStorage` and not in the account — the API has no column for it.

Collapsed, every entry keeps its icon; the label stays the link's accessible name and the `title`
carries label and hint, so the hint is hidden and never truncated. The active entry keeps the accent
colour, the group headings become hairlines, and the accordion is off — a heading with no label in a
64px column is a click that says nothing — so all sixteen entries show at once. The session footer
folds into the account's initial plus two icon buttons.

The wordmark leaves the menu but not the page: the attribution renders at the foot of **every**
screen (`AttributionFooter`, ADR 0006), including the three that come before a session — the first-run
setup, the sign-in form and the forced password change — and it ends with the installation's version,
alone at the right. The icons come from `lucide-react`, one glyph per entry.

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

The faceted search over the collection: the term, one of **three rankings**, typology, subject
category, entity type, level, a branch of the arrangement and a date range. The URL is the state, so a
filtered list is shareable and the back button works. Nothing is written.

The three rankings answer different questions, and the screen says which is which:

| Mode | What it orders by | When to choose it |
| --- | --- | --- |
| Lexical (default) | `ts_rank` over the generated `search_vector`, boosted by a tag or entity that matches | The archivist knows the term the title uses |
| Semantic | Cosine similarity between the term and the description's embedding | The archivist knows the subject but not the vocabulary of the fonds |
| Hybrid | The two fused by Reciprocal Rank Fusion (`RRF_K = 60`, window `RRF_DEPTH = 100`) | The mode that does not require the choice, at the cost of loading the model |

The numbers behind those sentences live in `docs/log.md`, next to the bench that produced them
(`testing/evaluation/retrieval_modes.py`), and not on this page: a page that stores a number which is
expected to move lies on the next run. What the screen does state is that the evidence is a small
labelled proxy set, and that the lexical mode is preferred when the term is known — the one place
where the two arms differ by a wide margin.

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

The decision is which tags and entities this description carries, and which category each tag belongs
to. The writes are `POST`/`DELETE /api/v1/documents/{description_id}/tags[/{tag_id}]` and the entity
pair (`CURATE`), plus `PATCH /api/v1/taxonomy/tags/{tag_id}` for the category. Linking and unlinking
are reversible: the revision stores the **whole list of names** on each side, and calling the same
route twice writes no revision.

Every entity shows the **origin of its link**: `IA` when the extractor wrote it, `confirmada` when a
person associated or confirmed it, and `não rastreada` for a link written before the column existed.
An unknown origin is never shown as the model's own. `Confirmar` associates an entity the extractor
already proposed without duplicating it: the link keeps its place and its origin becomes `HUMAN` —
the positive verdict the archivist could not record before (#135). Confirming a link that already
existed changes no names, so it writes no revision: the record of the confirmation is the link's
origin, and the description becomes `HUMAN_APPROVED`, which takes it out of the AI's queue.

!!! warning "The category is a decision about the vocabulary, not about this description"

    Changing a tag's category moves it for **every** description that carries the tag, and the screen
    says so next to the select. Choosing "sem categoria" gives the tag back to the AI classifier, which
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

The plan is reached from `/configuracoes` — deciding the rungs is setup work, not daily curation —
and the diagnostic stayed in the menu, under "Acervo", beside the tree it reads. With the plan gone,
the "Arranjo" group would have held a single line, so the group disappeared with it.

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Plano de arranjo — `/arranjo/plano` | approve or reject each proposed rung, and materialise the tree | yes — a decision can be reopened, and the materialisation has an undo |
| Diagnóstico do arranjo — `/arranjo/diagnostico` | none (the evidence; the fix is elsewhere) | yes (read only) |

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

The side panel materialises the tree: it always offers "Conferir impacto" first, and the
apply button stays disabled until the preview exists. Only approved rungs are materialised. The
preview and the apply share one planner, so the approved number is the written number. What the undo
restores is described under **the batch that does have an undo**.

### Diagnóstico do arranjo — `/arranjo/diagnostico`

The structural diagnosis, one section per issue, each with its count and its evidence (a section with
zero stays visible, because knowing the check ran matters). It offers **no silent correction**: every
row links to the screen where the fix is a recorded decision — the plan, the tree, or the
description's arrangement tab. The counts overlap deliberately (a Dossiê at the root is both `ORPHAN`
and `DOSSIER_WITHOUT_PARENT`), so there is no grand total.

## Catálogos

All three are reached from `/configuracoes`, under *Arranjo e catálogos*: they are the vocabulary the
work is written against, not the work, which is why the menu no longer carries them.

The two closed catalogues the archivist maintains and the collection vocabulary. None of them
deletes: a row retires with `is_active=false`, because the foreign keys are `SET NULL` and removing a
row would unclassify every description pointing at it while erasing the fact that it ever existed.

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Níveis de descrição — `/arranjo/niveis` | the ladder the arrangement is written against | yes (retire and reactivate) |
| Tipologias — `/arranjo/tipologias` | the diplomatic form the classifier proposes, and the descriptions it refused | yes (retire and reactivate; filing a description is a document revision) |
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

The screen also lists the descriptions the classifier refused. `GET /api/v1/typologies/refusals`
(`AUTHENTICATED`) returns one page of the descriptions whose best score stayed below the floor,
nearest miss first, with the label the run guessed and the score it saw. The list reads the same
predicate as the classifier's count and leaves out a description a curator has already filed, even
though its queue row remains. Choosing a typology there is `PATCH /api/v1/documents/{id}`
(`CURATE`): the dossier's own write, which records the revision and marks the description
`HUMAN_APPROVED`. It is reversible from the dossier, and the before/after stays in the trail. An
empty list means no refusal is open, not that the catalogue covers the collection — a description no
run reached has no row, and filing one removes it from the list without deleting the evidence. If no
typology fits, create or reactivate one in the catalogue on the same screen; there is no durable
verdict for "this description has no typology" yet.

### Vocabulário do acervo — `/vocabulario`

What *this* collection declares, as opposed to what the language or the software fixes. Two lists:

- **arrangement names** — `POST`/`PATCH /api/v1/vocabulary/arrangement-terms` (`CATALOGUE`): a token
  (`SMU`) or a whole code (`BR PRADAP`) mapped to the name the arrangement proposal suggests; the
  whole code wins over the last token;
- **collection terms** — `POST`/`PATCH /api/v1/vocabulary/collection-terms` (`CATALOGUE`): the
  spellings the collection carries and that are not subjects, typed so the guard recognises a place
  or a person name. What the name *is* is carried by the entity axis (`LOC`, `PER`), not by a state
  of the tag: the subject axis simply stops guessing at it.

What belongs to the Portuguese language itself — *rua*, *não identificado*, *303 anos*, a bare year
— lives in the language profile and does **not** appear here: changing it would change the meaning
the software gives to a word. Withdrawing a term does not delete it, and a withdrawn term is treated
as a subject again on the next classifier run.

## Assuntos

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Tags — `/assuntos/tags` | the weight, the duplicates, the merge queue, the banned terms **and the subject decision of each tag** | the merge yes (ledger); the purge yes (its own ledger); a subject decision yes (it can be taken back) |
| Categorias — `/assuntos/categorias` | the subject categories the classifier reads, **and what is inside each one** | yes (retire and reactivate) |
| Descobrir Categorias — `/assuntos/descobrir` | whether a proposed theme deserves a category | yes (the proposal writes nothing) |
| Não é assunto — `/assuntos/excecoes` | which terms leave the subject axis and have their spelling banned from becoming a tag again | yes (the ban deletes nothing, and the undo lifts the ban this decision planted) |

### Tags — `/assuntos/tags`

One route, five questions, one conversation: the archivist sees that `alvenarias` weighs little,
finds its near-duplicate and decides whether to absorb it. Four of the tabs are how they look; the
fifth, **Classificar**, is where the subject decision is taken, and it is where the home screen's two
subject cards land. The active tab is in the URL.

#### Relevância

Read-only: `GET /api/v1/taxonomy/tags/relevance/{method}`. The count shows what dominates the
collection; TF-IDF shows what is specific, punishing what appears everywhere. The two lists answer
different questions on purpose.

#### Similaridade

Pairs by trigram similarity, shown raw with the similarity score and both ids. The read is
`GET /api/v1/taxonomy/tags/similar`. The similarity does not say which spelling is the good one:
`'alameda cabral'` and `'al. alameda cabral'` score 1.000.

The decision is to merge: `POST /api/v1/taxonomy/tags/merge` (`CURATE`), after a dry run
(`POST /api/v1/taxonomy/tags/merge/preview`, a read that computes the same plan the write executes).
The panel always opens with the impact first: documents updated, links rewritten, tags absorbed,
spellings registered and repointed, and the one warning that must be read before the click —
`category_would_be_lost`, when the canonical has no category and an absorbed tag does, so the merge
would erase a subject classification.

The merge is **reversible**: the write is logged per absorbed tag in the merge ledger before
anything changes, and the undo (`DELETE /api/v1/taxonomy/tags/merge-log/{merge_id}`, `CURATE`)
restores the row, the links, the classification and the spelling state. The undo deletes only the
links the merge created, so it cannot detach a document that already carried the canonical. Rows can
also be marked across lines and unified as a cluster, which is how one merge spans several pairs
(`carlos de carvalho` appears in more than one row).

A marked selection has a **second destination**, and it is the other kind of write: **Banir N
marcadas** registers the spellings in `POST /api/v1/taxonomy/tags/stopwords` (`CURATE`), on the axis
chosen beside the button. Banning **deletes nothing** — the tags stay in the collection, linked and
reachable by search, and the step that removes them is the **purge** in the Stopwords tab, behind its
own preview and with a ledger that restores each tag. The marks survive the ban: the merge they were
made for is still possible.

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

The banned terms, and the destructive write in the taxonomy that keeps a ledger. The screen keeps
three things apart:

- **Banir** — `POST /api/v1/taxonomy/tags/stopwords` (`CURATE`) records that a term is not worth
  considering on one axis: `TAG` (the subject axis), `ENTITY` (NER) or `ALL`. A word has exactly one
  scope — re-banning it **moves** it — and banning **deletes nothing**. A ban typed here is recorded
  with `source=HUMAN`; the ban the *Não é assunto* screen plants is `EXCLUSION`, and the one a
  conflict resolution plants is `CONFLICT`. The list shows the scope on every term and the origin as
  a badge when it is not `HUMAN` — a term typed here is the default, and the badge marks the ones
  that arrived as a consequence of another decision.
- **Desbanir** — `DELETE /api/v1/taxonomy/tags/stopwords` (`CURATE`). Reversible.
- **Casamento** — `PATCH /api/v1/taxonomy/tags/stopwords` (`CURATE`) changes how an existing ban
  matches without re-banning it: a re-ban would overwrite the origin a conflict or the *Não é
  assunto* screen recorded. `TOKEN` blocks the word **and any name that contains it as a whole
  word** — the merged span `IPTU do Exemplo` — and `EXACT` blocks the spelling alone, which is what a
  generic word that starts a proper name needs: `alameda` blocks `alameda`, never `Alameda Cabral`.
  Only the `ENTITY`/`ALL` axes read it. Every entry of `domain_ner_exclusions` matches the exact
  spelling for the same reason: the conflict was about `casa`, not about `casa da memória` (#160).
- **Purgar** — `POST /api/v1/taxonomy/tags/stopwords/purge` (`CURATE`), after
  `POST /api/v1/taxonomy/tags/stopwords/purge/preview`. This is the write that deletes the tags. The
  preview lists the tags that would die, with their document count, their category **and where the
  ban came from** (`HUMAN`, `CONFLICT` or `EXCLUSION`), so a term banned with the archive in mind is
  told apart from one typed by hand; the apply button is disabled until the preview exists.

Each deleted tag is written to a **ledger** (`archive_stopword_purge_log`) before it disappears: the
snapshot of the row, the documents that carried it and the spellings that pointed at it. The purge
response carries the `purge_ids`, the Stopwords tab shows them in **Ledger das purgas**, and
`DELETE /api/v1/taxonomy/tags/stopwords/purge-log/{purge_id}` (`CURATE`) restores the tag, its links
and its spellings; an unknown id is **404** and a second attempt is **409**. The undo does **not**
lift the ban — the term is still a stopword, and the next purge lists the restored tag again.

!!! warning "The scope protects the other axis"

    The purge reads only `TAG`/`ALL`. A term banned on the `ENTITY` axis is a NER veto and can never
    make the subject purge delete a tag the curator kept — the two are stored in different places on
    purpose.

#### Classificar

Where a tag's subject is decided, and the tab the home screen's cards open. The read is
`GET /api/v1/taxonomy/tags/catalog` (`AUTHENTICATED`), filtered by `subject_state` and optionally by
`macro_category_id`, paged, and ordered by weight — the tag the most descriptions carry is the
decision worth taking first. It exists because the type-ahead cannot answer it: that one requires a
term and returns a top-N by weight, so a card promising "76 tags without a subject" had no read that
could mark which rows they were.

The state is a **partition**, and `ALL` is the absence of a filter rather than a state:

| `subject_state` | What it means |
| --- | --- |
| `PENDING` | No drawer and no verdict: nobody has decided. It is what the home card counts |
| `NOT_SUBJECT` | A person declared the tag is not a subject; the classifier stops guessing at it and its spelling is banned from becoming a tag again |
| `LOW_CONFIDENCE` | The classifier ran, was not confident enough to file the tag, and left it undecided |

The row carries the evidence (weight and the classifier's confidence) and exactly one of two
destinations, through `PATCH /api/v1/taxonomy/tags/{tag_id}` (`CURATE`):

- **a category** — the drawer the tag joins. The decision is **global**: it changes the badge of
  every description that carries the tag, and the screen says so before the click;
- **not a subject** — `macro_category_id=null`, which is the same write the *Não é assunto* screen
  makes. The tag stays in the collection and reachable by search, and the column alone would be a
  decision the next run overwrites, so the term is registered in `domain_subject_exclusions` **and its
  spelling is banned at `TAG` scope**, so the next ingestion does not recreate it. The reversal is
  `DELETE /api/v1/taxonomy/tags/subject-exclusions`, and it lifts only a ban this decision planted.

A producer, a place or a person is **not** a third destination. What the name *is* belongs to the
entity axis, where it carries a type (`LOC`, `PER`, `ORG`) that search and the public projection
read; a spelling that is both a tag and an entity is settled on
**Conflitos — `/entidades/conflitos`**, which bans the losing spelling and keeps a ledger. Declaring
the term not a subject is what takes it out of the subject queue; the entity is where it keeps its
meaning. The measurement behind the removed state still holds — `alfa` reaches 2,376 descriptions and
`cidade` 1,865, and forcing them into a category is a measured cause of the classification defect —
but the answer is now the entity and the exclusion, not a fourth state of the tag.

The same two actions apply to a **selection**, one request per tag, and the batch reports how many
tags it wrote and where. Nothing on this tab deletes: banning a spelling and purging the tags are in
**Stopwords**, each behind its own step, and the purge keeps a ledger with the undo of each tag.

### Categorias — `/assuntos/categorias`

The categories the subject classifier reads. `POST /api/v1/taxonomy/macro-categories` and
`PATCH /api/v1/taxonomy/macro-categories/{category_id}` (`CATALOGUE`) create, rename, describe,
retire and reactivate them; a retired category keeps its weight visible. Two honest notes the screen
gives: the **classifier label** is a curator override, not an improvement — measured on 44
hand-labelled tags, a phrase instead of a bare name scores 0.000 with 65% of the tags in one category
— and a **new category only takes effect when the classifier runs again**, because the worker's stamp
is the hash of the label set, which returns the tags to the queue on its own.

Each card opens on two tabs. **Descrições** lists the descriptions the category holds, ten at a time,
through the collection search (`GET /api/v1/documents?macro_category_id=`, `AUTHENTICATED`); the
card's badge counts **distinct** descriptions through the same join, so the number on the card and
the `total` of the list are one definition counted twice. A category with none says so — the retired
ones are not a defect. **Editar** is the form: name, classifier label and description.

The button on the row opens a **read-only preview** of one description — reference code, title, date,
level and typology, arrangement path, its tags with their drawers, and the review status — over the
list, so the description can be recognised without a round trip to the dossier. The panel writes
nothing: its **Editar** leaves for `/acervo/{description_id}?aba=descricao`. The open category, its
page and the previewed description live in the URL, so the back button closes the panel and the page
survives it.

### Descobrir Categorias — `/assuntos/descobrir`

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
whether the term is a place, whether the same spelling is also an entity, the drawer that would block
it and whether its spelling is already banned), and offers to register them with `source=RULE` or one
at a time.

Confirming plans and applies in one call: the write below consumes the same planner the preview route
uses, so the two cannot disagree. The preview is `POST
/api/v1/taxonomy/tags/subject-exclusions/preview` (`AUTHENTICATED`); it takes the terms and nothing
else, because a plan has no reason to declare and no provenance to report, and it answers
`applicable` and `blocked`. The **Vetar termos** box asks it as the typing settles (250 ms) and shows
the refusal **before** the click: a term whose tag already sits in a drawer is named with the drawer
while the archivist can still change it, and the write's own answer only confirms it. The box writes
every term that applies, so a partial refusal does not disable the button — only a list where **all**
terms are blocked does, because then the write would record nothing.

The write is `POST /api/v1/taxonomy/tags/subject-exclusions` (`CURATE`), and it does two things at
once: it registers the term in `domain_subject_exclusions`, so the subject classifier stops guessing
at it, **and it bans the spelling at `TAG` scope**, so the next ingestion does not recreate the tag
that was just decided about. **The ban deletes nothing**: the tag stays in the collection, stays
linked and stays reachable by search. Removing it is a separate act — the **purge**, in the Stopwords
tab, behind its own preview and with a ledger that restores each tag — and the purge preview says
which bans were planted here (`EXCLUSION`) and which by hand (`HUMAN`).

Two answers the screen has to show:

- a term whose tag already sits in a **drawer** is not applied: it comes back in `blocked` with the
  drawer that has to be emptied first, because "which drawer is this tag in?" is a question about the
  *tag*, answered on the tag catalogue, and a statement about a *term* must not un-file a human
  verdict. The code is `SUBJECT_EXCLUSIONS_BLOCKED` when nothing was applied and something was
  refused, `SUBJECT_EXCLUSIONS_PARTIAL` when some were applied and some refused, and `created` /
  `banned` / `blocked` carry the three answers;
- the route deliberately proposes nothing for the semantic half: the available signals lie, and a
  model that does not know how to abstain would answer confidently and wrongly.

The reversal is `DELETE` (`CURATE`, the screen's "restaurar"). It answers `removed` and `unbanned`,
and the lift is exact: only a ban this decision planted leaves with it. A spelling a person banned on
the Stopwords screen, or one a conflict resolution planted first, survives.

## Entidades

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Entidades — `/entidades/lista` | the type of a name, the spelling of a name, and whether two names are one | the type yes; the rename **yes** (one ledger row); the merge **yes** (one ledger row per absorbed entity) |
| Exclusões de NER — `/entidades/excecoes` | which spellings are subjects, not proper names, and the retroactive purge that follows | both **yes**: the veto row by its own `DELETE`, the purge by its ledger (`archive_ner_purge_log`) |
| Conflitos — `/entidades/conflitos` | whether a collision belongs to the subject axis or to the names, one pair at a time or a whole category at once | yes (one ledger row per pair, with the undo) |

### Entidades — `/entidades/lista`

The named-entity vocabulary, by weight or by similarity. Five decisions:

- **Reclassify the type** — `PATCH /api/v1/taxonomy/entities/{entity_id}/reclassify` (`CURATE`),
  only between `ORG`, `PER` and `LOC`. This is not renaming a label: the service also writes the
  anchoring synonym, so the extractor returns that spelling with the new type in every future run.
- **Renomear** — `PATCH /api/v1/taxonomy/entities/{entity_id}` (`CURATE`): corrects the spelling of
  one name, and it is **not** a merge. The previous spelling stays anchored as a synonym unless the
  archivist turns `keep_old_synonym` off, which is what keeps a future extraction of the old spelling
  resolving to this entity — and a typo is exactly the case where it should not. The write leaves one
  `RENAME` row in the same ledger the merge uses, so the screen's "desfazer" restores the name and
  drops the spelling it planted. A spelling another entity already carries is a **409** that names the
  twin and points at the merge, never a silent overwrite and never a bare structural conflict.
- **Excluir** an entity — `DELETE /api/v1/taxonomy/entities/{entity_id}` (`CURATE`), offered only on
  a row no description carries, where deleting loses no link. No undo.
- **Purgar órfãs** — `POST /api/v1/taxonomy/entities/orphans/purge` (`CURATE`): the same decision in
  batch. No undo.
- **Mesclar** — `POST /api/v1/taxonomy/entities/merge` (`CURATE`): the absorbed entities stop
  existing, their links move to the canonical, their spellings become synonyms, and an optional new
  name for the canonical makes the old one a synonym too. The decision is preceded by the preview
  (`POST /api/v1/taxonomy/entities/merge/preview`, a read): it returns how many descriptions gain the
  canonical, how many links are rewritten, which entities are absorbed and the warnings to look at,
  computed by the **same planner** the write executes. Entities have no proposal catalogue, but they
  do have a ledger: each absorbed entity is logged **before** anything changes, and the undo
  (`DELETE /api/v1/taxonomy/entities/merge-log/{merge_id}`, the screen's "desfazer") restores the row,
  its links, its spellings and the name the canonical lost. `GET /api/v1/taxonomy/entities/merge-log`
  is the trail, searchable by either spelling of each entry.
  The pair list is raw evidence, with both ids, because two rows can read almost the same name and
  the canonical is a choice the archivist has to be able to tell apart.

The merge has three doors and one panel behind all of them: the selection on **Relevância**, a pair on
**Similaridade**, and the **Mesclar pelo nome** card above the tabs. The card exists because the other
two are list-driven and the archivist controls neither list — relevance is ordered by weight and
capped, so two names carried by very different numbers of descriptions are never on the same page, and
similarity is trigram, the one measure that fails on the pair they are most sure about (`smu` and
`smcs secretaria municipal de comunicação social`: 68 descriptions against 1, and 0.045 of trigram
similarity). The card takes the names through the type-ahead the dossier's Assuntos tab already uses,
so it inherits the API's two-character floor instead of inventing one; it shows each name's weight, so
the canonical is chosen with the numbers in view; and **its list is its own** — it does not consume the
checkboxes of Relevância, and with fewer than two names nothing is written.

Reading is the other half of this screen, and the card opens into it. A name expands into the
**descriptions that carry it** — the collection search (`GET /api/v1/documents`) with `entity_id`,
paged ten at a time inside the card, so the badge above and the list's `total` are one number counted
twice; `testing/integration/api/controller/test_entity_documents.py` fails when they stop agreeing.
Clicking a row opens the read-only preview (`?descricao=`) that the category screen already uses, and
nothing in it writes. Its "Editar" lands on the dossier's **Assuntos** tab, which is where a
description's entities are added and removed. One card is open at a time, and `?aberta=`, `?offset=`
and `?descricao=` carry that state in the URL — so the back button closes the panel and a colleague
can be sent the exact view.

The card's second tab is the rename, and the **Renomear** button beside the name opens it. It is the
row's own affordance and never merges: the merge starts from two or more names and only renames the
canonical as a side effect.

### Exclusões de NER — `/entidades/excecoes`

The veto "this spelling is a subject, not a proper name". **Vetoing deletes nothing.** The write is
`POST /api/v1/taxonomy/entities/ner-exclusions` (`CURATE`), with a reason kept for audit, and the
reversal is `DELETE` (the screen's "remover veto"), which re-opens the term for future extractions.
One behaviour the screen states because it is not visible in the list: the block is **by token
boundary**, not by exact name (spaCy merges neighbouring tokens, so a banned `iptu` would not stop
`"IPTU do Batel"` under an exact comparison).

The retroactive half is a separate act, **Expurgar do passado**:
`POST /api/v1/taxonomy/entities/ner-exclusions/purge` (`CURATE`), after
`POST /api/v1/taxonomy/entities/ner-exclusions/purge/preview`. The preview lists every entity already
extracted from a banned spelling, with the descriptions that carry it, and the write consumes the same
plan. Each deleted entity is written to a **ledger** (`archive_ner_purge_log`) before it disappears:
the snapshot of the row, the documents that carried it, the spellings that pointed at it and the
`excluded_term` that justified it. The response carries the `purge_ids`, the screen shows them in
**Ledger dos expurgos**, and `DELETE /api/v1/taxonomy/entities/ner-exclusions/purge-log/{purge_id}`
restores the entity, its links and its spellings — **without** lifting the veto, so the next purge
lists the restored entity again. Use it to reverse the loss; use "remover veto" to re-open the term.

The conflict screen resolves the same clash with the same pair of writes, and it is reversible there
in the same shape: one ledger row per pair (`archive_conflict_resolution_log`), with the losing row,
its links and its spellings restored by the undo. Reaching the operation from either screen now
restores the same things.

This is the other half of the bidirectional governance: it records the curator or the judge saying
"this belongs to the subject axis", and it is stored apart from the subject-axis stopwords on
purpose, so a veto here can never make the subject purge delete a tag the curator kept.

### Conflitos — `/entidades/conflitos`

The same spelling on both axes: "is this a subject or a proper name?". Three reads answer three
questions, and reading only the first is what used to hide the judge's work:

- **Pendentes** — the live trigram scan (`GET /api/v1/taxonomy/conflicts/cross-domain`), annotated
  with the judge's verdict where there is one and filtered by `pair_kind`: "grafias diferentes" (a
  spelling question) and "nomes idênticos" (a structural question) are not the same list, and mixed
  together neither is visible. The same read takes `entity_type` (`ORG`/`PER`/`LOC`), because "a
  street is an entity" is a decision about a category of collisions and not about a pair.
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

#### Deciding a category at once

A collision is decided one pair at a time, but the decision the archivist is actually making is
categorical — "a street is an entity" — and a collection can hold dozens of the same spelling on both
axes. The batch, `POST /api/v1/taxonomy/conflicts/resolve/batch` (`CURATE`), applies one verdict to
the whole **selection** the list is showing: the same `pair_kind` and `entity_type` filters, the same
`threshold`, and nothing else.

The unit of the decision is the selection; the unit of the write is still the pair. Every pair is
planned by the same planner the single preview uses and written inside its own savepoint, so one pair
failing does not roll back the others, and every pair gets its own ledger row and its own
`resolution_id` — the undo stays per pair even though the click was categorical. A pair whose loser an
earlier pair of the same batch already removed is reported in `skipped` **with its reason**, never as
a failure: it is finished work, and calling it a failure is what once turned a clean batch into a wall
of red lines.

`limit` bounds one request, because a click that writes thousands of ledger rows is a click nobody
reviewed. `remaining` is the same read the list makes, taken again with the same filters, so the
number before the click and the number after it are one measurement — the screen cannot claim a
category is finished when the next page disagrees.

!!! note "A resolved pair leaves the live scan"

    The resolution deletes the losing row, so the trigram join cannot return it and the live list has
    nothing to annotate. That is why the work survives in the judge's queue and in the ledger, and
    why the `Decididos` and `Resoluções` tabs exist.

## Qualidade

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Trechos — `/qualidade/trechos` | which consumer stops reading a repeated excerpt | retiring **yes**; removing it from the catalogue is final |
| Regras — `/qualidade/regras` | whether a rule rewrites the text or only flags it | yes: retiring has a route back, and the retired rule stays on the screen |
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
- **Aprovar / rejeitar / aposentar / salvar escopo / remover** —
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
the rule would have lost. Retiring is the safe half of the pair — it is what you reach for when
a rule is wrong, so the way out of it has to exist.

An active `REWRITE` rule is the loudest thing on the screen, and the preview is what makes it
visible: a test rule once sat active and stamped the whole collection without matching anything.

An `LLM_CHECK` rule also names an **engine** and a **preset**, and both are chosen from the registry
rather than typed from memory: the two selects are fed by
`GET /api/v1/quality/cleaning-rules/engines`, which is the title-quality axis's own catalogue — the
same names `get_engine` validates against, so a model that retires stops being offered here in the
same change that retires it. The pair is checked when the rule is written, so a rule that cannot run
cannot be saved (the refusal is a `422` naming the options), and an empty engine stays legal: it
means the axis's default. A rule written before that check existed degrades instead of killing the
run — the validator logs the reason, validates deterministically, and its producer identity is the
"no model" one, so the queue and the panel's counter describe the run that actually happened.

### Anomalias — `/qualidade/anomalias`

What the quality validator marked, read-only (`GET /api/v1/documents` filtered to `NEEDS_REVIEW`,
optionally by anomaly reason). The counts by reason are the search's own facet over the whole
filtered set, and clicking one narrows the list. An empty queue has two very different causes and
the screen tells them apart: the collection is clean, or no rule that flags (a `VALIDATE` or
`LLM_CHECK` rule) is active — a `REWRITE` rule changes the text and never flags. The correction is
the human review of the record, in the dossier.

## Sistema

The machine, not the collection. Everything here belongs to whoever operates the installation, and
all three screens are reached from `/configuracoes`, under *Operação*: the menu kept what the
archivist consults while cataloguing, and this is not it.

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Workers de IA — `/sistema/workers` | whether to run a worker now | yes (the run's own configuration); a run's effects follow what it wrote |
| Execuções — `/sistema/execucoes` | none (the ledger and the grouped failures) | yes (read only) |
| Saúde do sistema — `/sistema/diagnostico` | none (database, models, storage, process) | yes (read only) |

### Workers de IA — `/sistema/workers`

The catalogue of the nine workers, in pipeline order, with the effective engine, preset and config on
the collapsed row — "with which model is this running?" is the question the screen exists to answer,
and here the answer is **read only**. What the installation is *set* to do is a screen of its own
(*Configuração dos Workers*, below), because the two questions are different: this one is what the
machine is doing. The row carries the queue — pending, processed, failed, last run — and the one
write is `OPERATE`:

- **Rodar agora** — `POST /api/v1/system/workers/{worker_name}/runs`. The run uses the effective
  configuration, adjusted only for this execution; nothing adjusted here becomes the default. Every
  run leaves a row in the run ledger, and a worker with a run in flight disables the button — the
  guarantee is the partial unique index in the database, and the screen only avoids offering what
  the database would reject.

The run panel's fields come from the contract, not from a text box: `declared_options` names the
options the worker accepts and, for a column list, the columns the AI text has
(`original_title`, `final_title`, `scope_content`, `admin_bio_history`, `provenance`), so the screen
renders a checkbox, a number or the columns themselves. The one free-form block is *Repasses ao
engine (avançado)*: a raw pass-through to the engine constructor, per run and never persisted, with
the keys the axis already passes (`model`, `device`, `host`, ...) as a hint. It is the named
exception of #120 — it exists for whoever knows the library, and the engine validates the value.

The panel itself offers no undo for a run. The reversibility of a run is the reversibility of what it
wrote — a merge undo, a materialisation undo, a conflict undo — and a worker that stamps its queue
does not redo its work just because it is run again. The panel marks **four** workers as outside the
human review block — the transfer, the conflict judge, the macro-categoriser and `worker_embedding` —
and only `worker_embedding` rewrites a *description*: it re-embeds a changed text even on an approved
document, the documented exception. The other three work on units that are not descriptions (a
staging record, a pair, a tag).

### Execuções — `/sistema/execucoes`

The run ledger, read-only: one row per execution, from the command line and from the panel, carrying
the **resolved** configuration the run used (so it stays readable after a preset changes in code),
the **effective worker options** (the columns it read, the floor, the cap — resolved when the run
started, so "which columns did run #N read?" has an answer), the duration, the outcome and who
asked. A row older than the options column says "opções não registradas nesta execução". Above it, the failures of the last 30 days grouped by root
cause (`GET /api/v1/system/failures`), which answer the question the ledger cannot: forty rows saying
the same sentence are one cause. Clicking a group filters the ledger below instead of opening a
second list, and a failure's reference is what is searched in the log.

### Saúde do sistema — `/sistema/diagnostico`

Four independent probes (`GET /api/v1/system/health`, `OPERATE`): the database with its counts, the
Ollama server with the models the presets require and which of them are missing, the thumbnail
storage, and the effective process configuration. Each probe answers on its own — a database that is
offline must not hide that Ollama is fine — and no secret value is ever shown: the process card
reports that a secret exists, never what it is. Nothing here writes.

## Configurações

The landing that gathers what the installation *is*, out of the way of what the archivist does every
day. It writes nothing of its own.

| Screen | Decision | Reversible? |
| --- | --- | --- |
| Configurações — `/configuracoes` | which setup screen to open | yes (read only) |
| Configuração dos Workers — `/configuracoes/workers` | the persisted default of each worker, and its history | yes (remove the row) |
| Usuários — `/configuracoes/usuarios` | who exists, what they may do, and where they are signed in | yes (deactivate and reactivate) |

### Configurações — `/configuracoes`

A page of cards, and every card opens a screen that already existed with the route it always had:
what changed is how it is found. Three tabs, in the order of the permission ladder they walk:

| Tab | Cards |
| --- | --- |
| Arranjo e catálogos | Plano de arranjo (`CURATE`), Níveis de descrição, Tipologias and Vocabulário do acervo (`CATALOGUE`) |
| Operação | Workers de IA, Configuração dos Workers, Execuções and Saúde do sistema (`OPERATE`) |
| Acesso | Usuários (`ADMIN`) |

The tab is in the URL (`?aba=`), so "the worker cards" can be sent to somebody. A tab the account
cannot fill is not rendered, and a `?aba=` naming one falls back to the first tab the account *can*
fill: a link that was valid for the sender still lands somewhere honest for the reader. Each card
carries the area its screen writes, and the entry that opens this page follows the same areas — the
rule is under *The menu hides; it never grants* above.

### Configuração dos Workers — `/configuracoes/workers`

What the installation is *set* to do, apart from what the machine is doing (issue #53). One card per
worker, in pipeline order, each carrying the persisted row of `archive_worker_settings` and its
revisions — both writes `OPERATE`:

- **Salvar padrão** — `PUT /api/v1/system/workers/{worker_name}/settings` writes the default. It is
  partial on purpose: an empty field keeps following the code, and the precedence is unchanged —
  `explicit argument > the archive_worker_settings row > the signature default`. The form renders one
  control per declared option (a column list as the columns the AI text has); `limit` is absent
  because a cap belongs to one execution, and `config` is still refused as an option, because it is
  a runner dataclass and not a JSON value. `engine_name`, `preset` and `db_batch_size` have fields of
  their own and are refused inside the options, which would otherwise be a second definition of the
  same field.
- **Conferir impacto** — `POST /api/v1/system/workers/{worker_name}/queue/preview` answers how many
  units the configuration the form is showing would leave in the queue, and writes nothing. It exists
  because the queue is keyed on the producer identity: saving another engine, preset or threshold
  re-reads the affected units by itself, and that cost has to be readable before it is paid. The
  number disappears as soon as a field changes, so it never describes a configuration the form no
  longer shows.
- **Voltar ao padrão do código** — `DELETE /api/v1/system/workers/{worker_name}/settings` removes the
  row. Every write leaves a revision
  (`GET /api/v1/system/workers/{worker_name}/settings/revisions`), listed on the card, so the default
  is reversible and the person who changed it is named.

A worker whose engine lives in the active `LLM_CHECK` rule (`quality-validator`) does not offer the
engine/preset choice here: a second place to choose the same engine would be a second source of
truth, so the card says where it lives and offers only the run parameters. The screen reads
`GET /api/v1/system/workers/settings`, which is not the panel's `GET /api/v1/system/workers` — the
panel counts nine queues, and this screen shows none of them.

A row written before the option validation is not a new mistake: the read ignores the option it can
no longer honour and explains it in the card's note ("Padrão salvo ignorado — …"), so the screen
answers with the code default instead of failing the queue counter. Saving the form again writes
only the fields it shows, which heals the row.

### Usuários — `/configuracoes/usuarios`

The accounts of the installation, the `ADMIN` surface. The writes are `POST /api/v1/users` (create),
`PATCH /api/v1/users/{user_id}` (name, role, active), `POST /api/v1/users/{user_id}/password` (reset)
and the session routes `GET`/`DELETE /api/v1/users/{user_id}/sessions[/{session_id}]` — all `ADMIN`.
Five facts the API enforces and the screen states:

- **the password created here is temporary.** The administrator typed it, so the account replaces it
  at the first sign-in, exactly like the CLI bootstrap;
- **deactivating ends every session of the account immediately**, which is what makes the flag real;
- **resetting the password ends every session** and lifts a lockout caused by failed attempts. It is
  reachable from the account's own row (**redefinir senha**), without expanding the card, and the
  confirmation names both consequences;
- **resetting your own account signs you out.** The administrative reset has no "keep this session"
  the way *Trocar senha* does, so an administrator who targets their own row ends the session they are
  standing on; the screen says so before the click and points at **Trocar senha** in the session
  footer, which keeps it;
- **the last active administrator cannot be deactivated or demoted** (`LastAdminError`, 409). It is
  the one lockout with no way back through the screen; the way in is the CLI on the host.

There is no delete. An account is deactivated, because the ledgers carry its name and its id, and a
decision whose author no longer exists is a worse record than a closed account. Revoking a session id
that belongs to another account answers 404 and not 200, because the id alone must not enumerate
other people's sign-ins; the row that is the archivist's own session is marked "esta sessão".

The account on this screen is **never the first one**. An installation with no account at all is
brought to life by the first-run screen it answers to the first visit, or by the CLI on the host, and
both of those close forever once an account exists — including a deactivated one (ADR 0011). After
that, this is the only surface that creates accounts.
