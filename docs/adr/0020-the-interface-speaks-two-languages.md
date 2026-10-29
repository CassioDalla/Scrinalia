# ADR 0020: The interface speaks two languages, and the API answers in the one it was asked

- **Status:** Accepted
- **Date:** 2026-10-27
- **Applies to:** the `apps/curator/src/i18n` catalogue, the `auth_users.locale` column and
  `PATCH /api/v1/auth/me`, the server's message catalogue, the queue and worker labels that leave
  the DTOs (#231), and the two halves of the i18n work — the infrastructure and the vertical slice
  (#45), and the sweep with its gate (#227).

## Context

The language rule in `AGENTS.md` is that the code is English and the user's text is Portuguese,
where a person reads it. For the curator SPA that rule was satisfied literally: the copy was
Portuguese and it lived in the components. By 1.6.0 the literal reading had become the one thing
the rule cannot survive — an institution that installs the system in another language cannot
translate 1,222 strings welded into 86 source files.

The server was designed for this day. A write route answers a stable English `code` beside the
Portuguese `message` (`RouteResponse`), and a refusal answers `error_code` plus `details`.
`apps/curator/src/lib/messages.ts` is the seam where a translation lands, and its map is
deliberately empty. Measured on 2026-10-27, the seam has to cover 44 route codes and nineteen call
sites; the numbers #45 opened with — 334 strings, thirteen call sites — date from 2026-10-09,
before the operations panel, the hint element, the conflict tabs and the origins page.

The state that this decision is taken against, measured by an AST scan of the SPA's 86 `.ts`/`.tsx`
files (JSX text plus string and template literals carrying a Portuguese diacritic or word; an order
of magnitude, not a copy census):

- **1,222 distinct strings**, 1,371 occurrences — 758 in the routes, 246 in `lib/`, 218 in the
  components.
- **109 sentences** mix text and an inline element (`<strong>`, a monospaced code); **45** interpolate
  a value.
- Three `Intl` constructions in `format.ts` fix `pt-BR`, one `toLocaleString("pt-BR")` sits in a
  route, and `index.html` declares `lang="pt-BR"`.

On the server:

- 44 `RouteMessageCode` members, about twenty of them interpolating facts (a count, a tag name,
  "N sessão(ões)").
- 62 `DomainException` classes; only `DuplicateEntityNameError` carries facts in `details`, because
  it is the only refusal the SPA recomposes.
- Four handler-level sentences (401, 403, 409, 500).
- Nine home cards and twenty worker `label`/`description` strings — 38 strings — are served as
  **data** in `CurationQueue`, `WorkerStatusDTO` and `WorkerSettingsItemDTO` and rendered verbatim.
  The copy gate scans `apps/curator/src`, so it cannot see any of them.

The documentation site already ships English and Portuguese, with English canonical (ADR 0010). The
interface does not, and the asymmetry has to be deliberate rather than accidental.

## Decision

### 1. Two locales, Portuguese canonical, English required by the type system

The interface ships `pt-BR` (the default and the product's voice) and `en`. The catalogue lives in
`apps/curator/src/i18n/`, one module per domain per locale; screens hold keys and never Portuguese.
`en` is declared as satisfying the shape of `pt`, so a missing translation is a **`tsc` failure**
and cannot be discovered by an archivist.

The asymmetry with the documentation is deliberate. There the reasoning is canonical in English and
Portuguese is a translation; here the person doing the work reads Portuguese first, so Portuguese
is the source and English is the translation that must exist. A missing English string cannot
silently fall back for the primary audience because the build does not allow it to be missing.

### 2. No i18n dependency

Two locales with one/other plurals do not justify a runtime. `Intl.PluralRules` covers the plural
(`descrições`, `sessões`), `Intl.DateTimeFormat` and `Intl.NumberFormat` cover the 220 call sites of
`formatDate`/`formatCount`, and a `Trans` helper covers the 109 sentences that carry markup. A
library's value would be extraction and ICU; its cost would be a build plugin, a second
configuration surface, and a runtime whose strings the copy pass cannot review in one place.

The trade is stated: this repository owns the plural and markup machinery, and a third language
with complex plural rules is the revisit trigger.

### 3. The locale follows the account, with the browser before it

`auth_users.locale` is nullable, and `null` means automatic. Before login — and for an account that
has never chosen — the SPA uses `navigator.language`, falling back to `pt-BR` for anything that is
not `pt*` or `en*`. The resolved locale is sent on **every** request as `Accept-Language`. The
account is the durable preference (principle VI); the URL is not a locale channel, because this is
an authenticated SPA with no anonymous, shareable page.

`PATCH /api/v1/auth/me` writes the preference and returns the `AuthUserDTO`. The selector sits in
the account menu, beside the password change, with an explicit "automático" option.

### 4. The API answers in the language it was asked

The server composes the sentence, not the client. A route's `message` and a refusal's `message` are
rendered from a catalogue keyed by identity — `RouteMessageCode` for the routes, the exception's
class name for the refusals, plus the four handler sentences — in the locale negotiated from
`Accept-Language`, falling back to `pt-BR`. A client that sends no header keeps exactly today's
behaviour.

The facts a sentence needs stay on the server: a route passes them to the renderer, and a refusal
carries them in `details`. `str(exc)` remains Portuguese and remains the fallback for a code with
no catalogue entry — the same fallback rule `routeMessage`/`refusalMessage` already follow, so a
client that knows neither still gets a sentence.

`routeMessage` and `refusalMessage` do not disappear: they remain the client-side override and the
fallback for a code the server's catalogue does not know yet. What changes is who owns the
sentence: the server, once.

### 5. A label is vocabulary; a sentence is a sentence

The API carries two kinds of user-facing text, and they do not have the same owner:

- **A sentence** reports what happened and carries facts a client cannot reconstruct — a route's
  `message`, a refusal's `message`, a worker's `pending_reason`, the four handler sentences. It
  lives on the server, keyed by code, rendered in the requested locale (§4).
- **A label** names something the contract already identifies — a screen, a queue, a worker, an
  enum member. Its stable identity travels in the payload (`ScreenId`, `queue.key`, `worker.name`,
  the enum code), and the text lives in the SPA's catalogue keyed by that identity, beside the rest
  of the interface's copy.

So the nine home cards (eighteen strings) and the twenty worker labels leave `CurationQueue`,
`WorkerStatusDTO` and `WorkerSettingsItemDTO`; the server keeps the identity, the count and the
sentences, and the route leaves too — a path is not text, so it lives with the screen catalogue in
the SPA (ADR 0021). A gate asserts that every `queue.key` and every worker `name` the contract
declares has a label in every locale, so a new queue fails a test instead of rendering a blank card.

A consumer that is not the SPA loses the ready-to-render label. That is accepted: the queue and the
worker labels are curator and operator presentation, and the public surface does not read them.

### 6. What is not translated

- **LLM prompts.** They reason about Portuguese text; translating one changes the model's task.
- **`SourceSchema` labels.** They are payload keys; translating one empties a column.
- **The collection and the user's data.** Titles, tags, entities, text templates, typologies and
  levels are the archivist's words, not the interface's.
- **Internal errors and logs.** English, per the language rule; only the sentence a screen can read
  is translated.
- **The license attribution.** Defined once and preserved by the license.
- **The contract's field descriptions.** API documentation, not screen copy; they stay Portuguese
  in `openapi.json` and are outside this decision.

Each exclusion is written where the extraction happens, not only here.

### 7. The copy pass comes after the extraction, in the catalogue

The extraction is mechanical: the current Portuguese moves to `pt/` verbatim, keyed by domain and
screen, with no editorial change. The manual copy pass then reviews `pt/` screen by screen and
checks the rendered screen in both locales. A change to a `pt` **value** does not break the type —
the key is the same — so the rule is procedural: every edited value reopens its English entry in
the same change. That blind spot is accepted and written down; a gate that reads git to detect a
changed value would be fragile and would fail for the wrong reason.

### 8. The gate, and the ratchet until the sweep ends

- No Portuguese literal outside `apps/curator/src/i18n/`.
- The retired-word canon of `lib/copy.ts` keeps scanning the catalogue, because the strings are
  still there.
- Every `RouteMessageCode` and every refusal class has an entry in every server locale.
- Every `queue.key` and every worker `name` the contract declares has a label in every locale.
- `format.ts` contains no locale literal.
- Until the sweep ends, `test_curator_copy.py` keeps a `file → count` pending list that only
  shrinks; a new file with Portuguese fails immediately.

## Rationale

- **One definition of each sentence.** Translating on the client would require moving the facts of
  about twenty route messages — and of the one refusal that carries them — into `details`,
  duplicating a sentence the server already owns, and would leave the future public surface unable
  to answer in another language.
- **Portuguese canonical.** The archivist reads Portuguese first, and a fallback to English for a
  missing translation is the failure mode this product cannot have. The documentation chose the
  inverse because its reader is whoever reads the code; both reasons live in an ADR so the
  asymmetry is not read as an accident.
- **Account plus browser.** The preference is durable intent, and login and setup exist before any
  account. A browser-only choice would not survive a device change; a URL prefix would add a router
  dimension to a surface with no anonymous pages.
- **No dependency.** The type system already gives the parity a runtime library would give, and the
  copy pass needs the text in one reviewable place.
- **One rule for text.** A label is looked up by the identity the payload already carries; a
  sentence is rendered where its facts are. Keeping the labels on the server would put the home
  screen's copy in Python while every other label lived in TypeScript.
- **The split.** Infrastructure plus a vertical slice is one release's work; the sweep of 1,222
  strings and its gate is another, and mixing them would hide the copy edits inside a mechanical
  diff.

## Consequences

Positive:

- The interface matches the documentation: two languages, and a second installation can be
  translated without editing the screens.
- The copy of a screen lives in one file, and the copy pass can review it without opening 86
  components.
- The first screen's copy is inside the copy pass and the gate, and a queue added to the service
  cannot render an untranslated or blank card.
- The seam `messages.ts` promised is proven end to end, including a server answer.
- The gate makes re-accretion deliberate: a new Portuguese literal is a failing test, not a habit.

Negative, accepted:

- A `pt` value change does not invalidate its English counterpart; the type sees keys, not text,
  and the discipline is procedural.
- The English catalogue ships in the bundle (roughly 15–20 KB gzip) until it is code-split.
- A browser in English shows the login screen in English even for an account configured in
  Portuguese; the account's choice applies after sign-in.
- The server now keeps two copies of some user-facing text — the exception's `str(exc)` and the
  catalogue entry. The catalogue is the one the client reads; the fallback is what keeps a client
  without a catalogue working, and a test pins that every code has an entry, not that the entry
  repeats `str(exc)`.
- A third language with complex plurals would reopen the no-library decision.
- Three DTOs lose `label`/`description` (`CurationQueue`, `WorkerStatusDTO`,
  `WorkerSettingsItemDTO`), so a client that is not the SPA must carry its own labels. Accepted:
  they are curator and operator presentation.

## Alternatives considered

- **react-i18next.** The standard, with mature `<Trans>` and plurals. Rejected for two locales and a
  copy pass that wants one file per domain: it adds a dependency, a provider and symbolic keys
  without solving the extraction.
- **Lingui.** Compile-time extraction and ICU plurals with a small runtime. Rejected because its
  message id is the source text, which puts the copy back in the 86 files the sweep is trying to
  empty; with symbolic ids it would still add a build plugin and PO files for two locales.
- **English canonical in the interface too.** Rejected: it rewrites 1,222 strings into English
  before anything can be translated, and makes the primary audience read a translation of its own
  product.
- **The client translates the server's sentences by code.** Rejected: the facts of about twenty
  route messages — and of the one refusal that carries them — would have to travel in `details`,
  the sentence would be defined twice, and the API would stay Portuguese-only for any other
  consumer.
- **Keep the labels in the DTOs and translate them on the server too.** Rejected: it splits one
  rule — screens and enum labels in the SPA, queues and workers in Python — and keeps the home
  screen's copy outside the pass that reviews it, although the identity the client needs is already
  in the payload.
- **Browser-only locale.** Rejected: no durable preference across devices, and the account would
  remain monolingual.
- **A locale prefix in the URL.** Rejected: a router dimension for an authenticated SPA with no
  anonymous, shareable page.
- **Stay Portuguese-only.** Rejected: it fails the reason the language rule exists — an institution
  installs the system in its own language.

## Revisit trigger

- A third language, or one whose plural rules are not one/other.
- The English bundle becomes a measured performance problem.
- The copy pass changes values often enough that the type's blindness becomes a defect instead of a
  discipline.
- The public site needs a locale the API cannot negotiate.
- The installation needs an administrator-set default language, distinct from the account's choice.
