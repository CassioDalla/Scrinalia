# ADR 0021: The URL speaks the interface's language

- **Status:** Accepted
- **Date:** 2026-10-28
- **Applies to:** `apps/curator/src/lib/screens.ts`, `apps/curator/src/router.tsx`,
  `apps/curator/src/lib/queues.ts`, the query keys the router validates, and the paths the guides
  quote (#239, #246).

## Context

ADR 0020 gave the interface two locales: the copy moved to a typed catalogue, the account chooses
the language, and the API answers in the language it was asked. The screen paths did not move with
it. The 28 entries of `apps/curator/src/lib/screens.ts` — 27 fixed paths and the dossier's
`/acervo/$descriptionId` — are still Portuguese, and so are the query keys the router validates.

That was coherent while the interface was Portuguese-only. With two locales it is a question, and
#239 asked it directly: should the paths be translated to English, so the code's language and the
URL's language stop disagreeing?

The state the decision is taken against, measured in this checkout on 2026-10-29:

- **28 screens** in `lib/screens.ts`; the router declares the same paths and the copy gate pins the
  pair.
- **12 `search={{…}}` call sites** in `apps/curator/src`, spelling the keys `aba`, `raiz`, `termo`,
  `modo`, `worker`, `run` and `ancestor_id`. The tabs themselves are Portuguese ids:
  `?aba=classificar`, `?aba=execucoes`.
- **Nine home cards**, of which **three** carried a query string through the contract before #246,
  and **two of those spelled the tab in Portuguese**
  (`/assuntos/tags?aba=classificar&subject_state=LOW_CONFIDENCE` and `?…=PENDING`).
- **48 `to="/…"` literals** outside the two catalogues, typed by TanStack Router, plus the paths
  quoted throughout `docs/guides/`.

Translating the path alone would therefore produce `/collection/list?aba=classificar`: the URL
would still be bilingual, and the argument for the rename would be gone. The cost was never the
language either — it was the four owners of the path (ADR 0020 §5).

## Decision

### 1. The path is an identifier, not copy

A screen never renders its own path. The person who types `/assuntos/tags` is the archivist the
product is written for, and Portuguese is the product's voice (ADR 0020 §1). The URL is not a
locale channel (ADR 0020 §3), so the path has nothing to follow except the interface's language —
and that language is Portuguese.

The documentation quotes a path the way it quotes `HUMAN_APPROVED`: a value to copy exactly, not a
sentence to read. A guide that translated `/assuntos/tags` would be a guide whose instruction does
not navigate.

### 2. The query keys are part of the same decision

A URL is a path **and** its query. The router reads `aba`, `raiz`, `termo` and `modo` from the
address bar, and the API's own filter names (`status`, `subject_state`, `worker`) appear beside
them. If a path is ever translated, the query keys move in the same change; translating one half
leaves the half that carries the interface's words.

The values are identifiers too. `classificar` is the tab's id, not a sentence on the screen: the
label the archivist reads comes from the catalogue, and the id survives a translation of the label
for the same reason `PENDING_AI` does.

### 3. The path has one owner, and it is the SPA

`apps/curator/src/lib/screens.ts` declares every screen's path, `router.tsx` declares the same
paths, and the copy gate (`testing/unit/curator/test_curator_copy.py`) fails when the two disagree.
The home screen's queue destinations moved beside their copy in `lib/queues.ts`, keyed by
`QueueKey`, and read the path from `SCREENS` (#246). The API carries the queue's identity, its
count and its sentence — never a path.

That is what makes a future rename one file plus the router and the documentation, instead of a
contract change and a second list inside a route.

### 4. The public site decides its own URLs

The public surface is a separate surface with its own reader. Its paths are not the curator's
paths, and this decision does not bind it: when it exists, it chooses a scheme for the audience it
serves.

## Rationale

- **The URL is the interface's language, not the code's.** The code is English and the URL is
  Portuguese for the same reason the screen is: the first is read by whoever maintains it, the
  second by the archivist. ADR 0020 already drew that line for every other string.
- **English paths would not buy a monolingual URL.** Three of the nine queue destinations carried a
  query, and two of those spelled `aba=classificar`; the 12 `search={{…}}` call sites are the same
  Portuguese vocabulary. A rename that stops at the path leaves the question open.
- **The cost is the owners, not the language.** #239 measured a rename before #246 as
  `screens.ts`, `router.tsx`, `QUEUE_CATALOGUE` through the contract, `IMPLEMENTED` in
  `InboxRoute.tsx`, the 48 typed links and the guides' citations. #246 removed two of those owners
  and gated the remaining pair, and this decision keeps the rename a single file.
- **No bookmark breaks either way.** There is no installation, account or user today, so the window
  is free. That argues for taking the decision now, not for spending the window on a rename that
  does not solve the problem it was proposed for.

## Consequences

Positive:

- The path stays stable while the interface gains a second language; no guide, bookmark or typed
  link breaks for a rename that would not make the URL one language.
- A rename is one owner plus the gate that pins it, and the queue destination is inside the same
  type-checked catalogue as the rest of the SPA's copy.
- A second installation that translates the interface does not inherit English paths it never
  chose, and it does not have to translate the route table to get its own language.

Negative, accepted:

- **An English-speaking operator sees Portuguese words in the URL.** They are identifiers, not
  sentences; the screen around them is translated, and the documentation quotes them literally.
- **The query keys are Portuguese too.** Typed router search keeps them in one place, but their
  spelling is part of the address and cannot be translated without the same rename.
- **The public site cannot reuse the curator's paths as its public scheme.** It is a different
  reader and a different address space; the decision is deferred to it.

## Alternatives considered

- **English paths.** Rejected: it leaves the query keys Portuguese, so the URL stays bilingual,
  and it pays the rename cost without the benefit that motivated it.
- **Translate paths and query keys together.** Internally consistent, but it breaks every guide
  citation and every typed link to buy a URL that is still one language — just a different one.
  The archivist reading Portuguese would get English identifiers and Portuguese copy.
- **A locale prefix (`/pt/…`, `/en/…`).** Already rejected by ADR 0020 §3: a router dimension for an
  authenticated SPA with no anonymous, shareable page. A prefix would also make every existing path
  a redirect.
- **Keep the path in the contract, as it was.** Rejected by #246: it makes every screen rename a
  contract change and gives the path a second owner on the server, where nothing can read it.

## Revisit trigger

- A second installation whose interface is not Portuguese: then the path must be English, because a
  lingua franca is the only readable answer that is not the product's voice — and the query keys
  move in the same change.
- The first external link to a screen — an e-mail, a report, a ticket from an institution. That is
  the day the URL stops being navigation and becomes a public identifier.
- The public site decides a URL scheme that has to match the curator's.
- A language whose words make a path ambiguous, offensive or wrong in the collection's vocabulary.
