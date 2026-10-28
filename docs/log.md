# Documentation log

One entry per triage round (ADR 0010). This records the **judgement**, not the writing: the commit
range that was looked at, and one line per page with the verdict and the reason.

The verdicts are `created`, `updated` and `no-change`. The `no-change` line is the one that matters
most: it says a page was reported stale, somebody read the change, and the text still holds — which
is what keeps the next round from re-reading the same range. A triage round that only ever reports
`updated` is rewriting instead of maintaining.

`docs/_hooks/freshness.py` reads the last range as a floor: everything up to its end is closed, so
only what landed after it is reported. The format is deliberately rigid, and
`testing/unit/docs/test_docs_frontmatter.py` pins it: the range is a `- **Range:** `start..end`` line
with short or full shas, and part of a `## <date> — <title>` entry.

## 2026-10-08 — the documentation base

- **Range:** `2b10f14..4681067`
- **Pages:**
  - `index.md` — created (the front door of the site)
  - `guides/install.md` — created
  - `guides/operate.md` — created
  - `guides/curate.md` — created
  - `guides/data-model.md` — created
  - `adr/0010-documentation-coverage-and-freshness.md` — created (the decision this log serves)
- **Divergences the writing surfaced, and the verdict on each** (every one read in the code before
  the edit; the code fixes are separate commits, not documentation edits):
  - `.env.example` carried the reference collection's `DB_NAME` — **fixed** (a fresh clone defaulted
    to somebody else's catalogue name), and `guides/install.md` was updated in the same change, which
    is the loop this log exists to record.
  - `AGENTS.md` listed the environment variables without the 14 `AUTH_*` and without
    `WORKER_RUNTIME_MAX_WORKERS` — **fixed**; the table in the install guide is now the complete one
    and the coverage gate keeps it that way.
  - The screen count was wrong in three places (23 menu entries, 24 routes, "25" in the draft of
    ADR 0010) — **fixed** to the measured 24, with the menu's 23 explained on the page.
  - `runner.py`'s comment put `macro-category` last, against its own `PIPELINE_ORDER`; the `README`
    claimed every worker stamps the document, which is false for `thumbnail` and `conflict-judge` —
    **both fixed**.
  - Left open as **code**, not text, and documented as behaviour on the page: the cleaning rules have
    no reactivation route although the screen says deactivating is reversible;
    `POST /taxonomy/tags/suggest-macro` writes nothing and declares `CURATE`; and the inbox's
    `IMPLEMENTED` set does not list `/entidades/conflitos` or `/qualidade/anomalias`, which exist.

## 2026-10-08 — the CPU build of torch

- **Range:** `4681067..b3db7e2`
- **Pages:**
  - `guides/install.md` — **updated**: the lockfile no longer carries the CUDA runtime. `torch` comes
    from the CPU-only index now (measured: 3.46 GB → 0.66 GB, and 2.19 GB of the old lock were
    `nvidia-*` packages), so the paragraph that justified `CUDA_VISIBLE_DEVICES=""` by the wheel was
    no longer true: the variable covers the installation that re-locks for a GPU, and the routes to
    CUDA that do not pass through torch. The "To use a GPU instead" list gained the re-lock as its
    first step, because without it the GPU presets have no wheel to run on.
  - `guides/install.pt.md` — **updated**: the same section, same structure.
- **One front-matter decision in this change:** `pyproject.toml` joined the page's `sources:`. It is
  where the index decision lives, and it was the one install-time fact the page did not track — which
  is why the report had not been able to see the change coming. It is also why this entry's range
  reaches back to `4681067`: the page was already stale against the dependency bumps the previous
  round closed, and adding the source is what made it visible.

## 2026-10-08 — the suite's own cost

- **Range:** `b3db7e2..e8a7a61`
- **Pages:**
  - `guides/data-model.md` — **no-change**: the only thing the page takes from `testing/conftest.py`
    is `archive_error_fingerprint`, mirrored into the test schema, and the story of a schema built by
    `create_all` instead of Alembic. Neither moved. What moved is test infrastructure — the Litestar
    application built once per session instead of once per test, and the argon2id cost lowered for
    the suite — and the page does not describe either.
- **A gap worth knowing, not a verdict:** `guides/install.md` and its translation also mention
  `testing/conftest.py` (the sentence about the test schema not being built by Alembic), but they do
  not declare it in `sources:`, so the report does not track it. Leaving it out is defensible — the
  mention is incidental to an install guide — but it means that sentence can go stale in silence, and
  this is the note that says so rather than a claim that the page is current.

## 2026-10-09 — the roadmap leaves the repository

- **Range:** `becba5e..cb85181`
- **Pages:**
  - `guides/operate.md` — **updated**: two sections appended, *Measuring the collection* (the query,
    and the one stamp that does not name its producer) and *Known limits and accepted trade-offs*.
  - `guides/operate.pt.md` — **updated**: the translation of both sections, with the Portuguese
    anchors the build actually emits.
  - `index.md` and `index.pt.md` — **updated**: the pointer to the retired page becomes the open
    issues and their milestones, and the sentence about the current state now names the limits page.
  - `adr/0009-authentication-and-authorization.md` — **updated**: the gap it recorded in the retired
    page now points at the limits section. An ADR is a page like any other for freshness, and this was
    the only reference to a *current* fact rather than to history.
- **The pages that did not need work, and that is the finding:** the retirement was expected to move a
  safety list and a set of failure modes. Both were already documented under the gate —
  `guides/curate.md` owns "what has no way back" and the arrangement undo, `guides/operate.md` owns the
  reprocessing window and the single-process assumption, `models/taxonomy.py` owns the classifier's
  baseline, and `AGENTS.md` owns the failure modes. So the move was the two new sections above, and the
  rest was deleted as duplication rather than relocated.
- **Not carried over, on purpose:** the retrieval measurements (MRR and Hit@10) and the collection's
  own state. A page that stores a number which is expected to move is a page that lies on the next run,
  and those belong to the open work that measures them.
- **A defect the change exposed, fixed in it:** the in-site link check resolved an anchor against the
  canonical page even when the linking page was a translation — the opposite of what its docstring
  states and of what the build produces. Measured on the built site, the Portuguese page keeps the
  Portuguese anchor. The check now bites in both directions; before the fix it accepted a link that
  would answer 404 in the browser.

## 2026-10-09 — the menu collapses to an icon rail

- **Range:** `cb85181..0b41007`
- **Pages:**
  - `guides/curate.md` — **updated**: a new *The menu collapses to icons* subsection, plus a clause in
    the introduction pointing at it. It records what the shell now does — the control in the menu's own
    header, the 64px icon column, the choice remembered by the browser in `localStorage` (presentation
    state, not an account setting), the label kept as the link's accessible name with the hint carried
    by the `title`, the active entry keeping the accent colour, the section headings becoming hairlines
    — and that the wordmark leaving the menu does not touch the attribution, which `AttributionFooter`
    renders at the foot of every screen (ADR 0006). Every claim was read in `AppShell.tsx` and looked
    at in the SPA in both states, reload included.
  - `guides/curate.pt.md` — **updated**: the translation of the clause and of the subsection.
- **The sentences that did not move:** what the page already said about the menu is still true —
  twenty-three entries, one route that is not an entry, the permission filter that hides a group and
  never grants, and the mirror that cannot grant. Collapsing is presentation and does not touch any of
  it.
- **Not documented, on purpose:** the twenty-three glyph choices. The code names one per entry and a
  page that listed them would go stale the first time somebody picks a clearer one; what the page owes
  the reader is where the icons come from and what the collapsed entry keeps.

## 2026-10-09 — the setup screens move behind a Configurações landing

- **Range:** `0b41007..bec40af`
- **Pages:**
  - `guides/curate.md` — **updated**: the introduction (23 menu entries → 16, 24 screens → 25, and what
    the cards are), *The menu hides; it never grants* (the card rules: hidden by `can()`, a tab with
    nothing visible not rendered, the entry present while at least one card is reachable, and the
    direct URL that explains itself), a new *Configurações* screen section with its three tabs and
    eight cards, and one pointer in each section whose group left the menu — Arranjo (the plan is a
    card; the diagnostic moved into "Acervo"), Catálogos and Sistema. The per-screen sections stayed
    where they were: what they document did not change.
  - `guides/curate.pt.md` — **updated**: the translation of all of the above.
  - `guides/operate.md` — **updated**: one sentence, and it is why this page was reported at all — it
    called the operations panel "the `Sistema` section of the SPA", and that section no longer exists.
    It now says the three cards of `/configuracoes`, under *Operação*.
  - `guides/operate.pt.md` — **updated**: the same sentence, plus the section heading, which carried a
    "(Sistema)" in parentheses.
- **A finding the report produced:** `guides/operate.md` went stale for a reason that has nothing to do
  with the workers it documents — it declares `apps/curator/src/router.tsx` among its sources, which is
  what let the report catch a navigation fact stated in the operations guide. The declaration earned
  its keep, and it is the argument for keeping the incidental sources rather than trimming them.
- **Deliberately not documented as done:** the worker settings split, the issue's second bullet. The
  panel still mixes configuration and the machine view; that work is issue #53, and the pages describe
  the screen as it is today.

## 2026-10-09 — the first administrator, and the window the lock cannot close

- **Range:** `bec40af..8dde39f`
- **Pages:**
  - `adr/0011-first-run-setup-without-an-open-door.md` — created. It amends ADR 0009 §4, §6 and the
    operational consequence on the first administrator, and it records the measurement the issue's
    proposed guard did not survive: `INSERT … SELECT … WHERE NOT EXISTS` **is not atomic** under READ
    COMMITTED (two sessions, two rows), while `LOCK TABLE auth_users IN EXCLUSIVE MODE` before the same
    predicate serializes the decision (the second call waits, inserts nothing, answers 409). It also
    records why the steady state must answer before hashing — `needs_setup` is public, and the hash is
    ~42 ms measured — and the accepted cost: the lock closes the race, not the window.
  - `adr/index.md`, `adr/0009-authentication-and-authorization.md` — **updated**: the index row, and
    three "amended by" pointers where ADR 0009 states the rule that changed (§4's open surface, §6's
    first administrator, the "what an installer must read" consequence). The old text stays: an ADR is
    the record of what was decided, not the current count.
  - `guides/install.md` — **updated**: step 6 is now both doors to the same account (the first-run
    screen and the CLI), says why the CLI's password is temporary and the screen's is not, that both
    close forever once any account exists, and names the window; the container section gained the
    alternative to `exec`. Two sources were added so the claim is trackable —
    `setup_controller.py` and ADR 0011 — plus `SetupForm.tsx`.
  - `guides/install.pt.md` — **updated**: the same step and the same container paragraph.
  - `guides/operate.md` — **updated**: one clause in the authentication-limits bullet — the first
    account is a window, and `{"needs_setup": true}` on a reachable instance is an invitation. ADR 0009
    and ADR 0011 were added to its `sources:` (the bullet cites both, and neither was declared).
  - `guides/operate.pt.md` — **updated**: the same clause.
  - `guides/curate.md` — **updated**: one paragraph at the end of *Usuários*, because that section owns
    the account surface and claimed nothing about how the first account appears: it says the account on
    that screen is never the first one, and that after the first account the screen is the only surface
    that creates accounts. ADR 0011 joined its `sources:`.
  - `guides/curate.pt.md` — **updated**: the same paragraph.
- **The sentences that did not move:** the curation guide's screen count and menu count — the setup
  form is not a route (`SetupForm` renders in the shell's slot, like `LoginForm`), so the router still
  declares 25 screens and the menu 16 entries. No table, no column and no migration landed: the route
  reads `auth_users`, which the data-model page already documents, and the settings are unchanged.
- **Verified rather than assumed:** the two new operations were exercised end to end against a
  throwaway database with `curl` — 422 on a weak password, 201 with `role: ADMIN`,
  `must_change_password: false` and a `HttpOnly; SameSite=lax` cookie, `/auth/me` answering with that
  cookie, 409 with `SetupAlreadyCompleteError` on the second call, and `needs_setup` flipping to
  false. The steady-state 409 costs ~1.7 ms, which is the cheap-read path and not a hash. A
  cross-origin POST to the setup route is refused 403 by `origin_guard`.
- **Not verified, and named here so nobody assumes otherwise:** the setup screen itself was not looked
  at in a browser. Headless Chromium in this environment dumps core before rendering, so the evidence
  is `tsc`, ESLint, the Vite build and the bundle carrying the screen's text — not pixels. The Tailwind
  tokens used are the ones `LoginForm` already uses.

## 2026-10-09 — recovery gets a front door

- **Range:** `71781bf..6118170`
- **Pages:**
  - `guides/operate.md` — **updated**: a new *Recovering access* section, because the page owned the
    path in a single bullet of its known limits — "the administrator, or the CLI on the host" — which
    names it without saying how to walk it. The section states which door applies, the administrator's
    route on the accounts screen (temporary password, sessions ended, lockout lifted, no undo) and the
    host's route with the four CLI commands, and it records the two absences (no e-mail, no
    reset-token table). `domains/identity/cli.py`, `domains/identity/services/auth_service.py` and
    `api/controllers/users_controller.py` joined its `sources:`: the section is a claim about them and
    they were untracked.
  - `guides/operate.pt.md` — **updated**: the translation, same commands, and the two in-page anchors
    rewritten to the Portuguese the build emits (`#recuperar-acesso`).
  - `guides/curate.md` — **updated**: the page described the accounts screen and never the sign-in
    screen, which is where recovery now begins. A new *Signing in, and forgetting the password* says
    the form is not a route, that a failure is one sentence on purpose, and that the disclosure states
    the path without promising a message. The accounts section went from four facts to five, adding the
    self-reset that signs the administrator out and the row action that reaches the reset at all.
    `components/layout/LoginForm.tsx` and `PasswordChangeForm.tsx` joined its `sources:` — the `routes/**`
    glob already covered `UsersRoute.tsx`.
  - `guides/curate.pt.md` — **updated**: both, in the SPA's vocabulary.
- **Verified rather than assumed:** the two screens were **rendered**, not merely built — the API on a
  throwaway database, the built SPA served at the same origin, driven through CDP. The disclosure's
  four sentences are legible and the recovery line wraps cleanly; the accounts row shows the new
  *redefinir senha* beside *desativar*; clicking it opens the card and `document.activeElement` is the
  password input, so the focus claim in the code comment is measured and not asserted; the self-reset
  warning renders in the warn tone for the account's own row; and `bg-(--color-warn)/5` is in the
  emitted CSS as `color-mix(… var(--color-warn) 5% …)`, not as the invalid bracket form.
- **A method note for the next round:** the full `chromium-<n>/chrome-linux64/chrome` renders here once
  `HOME`, `TMPDIR` and the two `XDG_*` variables point **inside the workspace**; pointed at the real
  `$HOME` it dumps core, which is the failure the previous entry recorded. The screenshots came from
  that binary, not from `chrome-headless-shell`.
- **What did not move:** the screen count (25) and the menu count (16) — no route was added, and
  `LoginForm` renders in the shell's slot; the settings table — the issue forbids a new setting and none
  was added; the data model — no table, no column and no migration; and the API contract, which has
  carried the reset operation since ADR 0009.
- **Not carried, on purpose:** the CLI's own `list`/`activate` behaviour beyond the two commands the
  recovery path needs. The install guide already owns the CLI as the bootstrap, and duplicating its
  whole surface here would create a second place to correct.

## 2026-10-09 — the interface gets one name per screen and one verb per action

- **Range:** `6118170..f731d2e`
- **Pages:**
  - `guides/curate.md` — **updated**: the page named screens by their old headings, and the headings
    are now the menu's labels — `Diagnóstico` split into *Diagnóstico do arranjo* and *Saúde do
    sistema*, which is the ambiguity issue #23 was filed for. A new *One name per screen, one verb per
    action* states the copy canon the page now uses: `lib/screens.ts` as the one record per screen
    (route, label, hint) that the menu, the settings card and the `<h1>` all read, the header's four
    slots with the status line under the subtitle, and the verb table of `lib/copy.ts` — including
    why `Aposentar` (a catalogue row) and `Desativar` (an account) are deliberately two words. The
    prose followed the verbs: `Unificar` → `Mesclar`, `desativar` → `aposentar` for the `is_active`
    catalogues. `components/layout/PageHeader.tsx`, `lib/screens.ts` and `lib/copy.ts` joined its
    `sources:` — the section is a claim about all three and none was tracked.
  - `guides/curate.pt.md` — **updated**: the translation, same canon, in the SPA's vocabulary.
  - `guides/operate.md` — **no-change**: the report named it because its `sources:` carry the three
    `System*Route.tsx` files, and this round moved the health screen's label to *Saúde do sistema* and
    the run button's word to `Rodar agora`. The page names those screens by **route**
    (`/sistema/diagnostico`, `/sistema/workers`), never by label, so no claim in it stopped being
    true; the field the worker panel lost ("Quem está alterando") was never documented there. Nothing
    was edited to quiet the report.
- **Verified rather than assumed:** every one of the 25 routes was **rendered**, not merely built —
  the API on a throwaway copy of the development database, the built SPA served from the same origin,
  screenshotted through CDP at 1440px. The screens show the heading equal to the menu label
  (`Categorias` / *As gavetas de assunto* / the count, in that order), the two renamed screens
  (`Saúde do sistema`, `Nível de descrição` → `Níveis de descrição` on the settings card and the
  heading), `Aposentar` where the catalogue row was `desativar`, `Rodar agora` where the same panel
  had `Executar agora` beside it, `Mesclar` where the merge panel said `Unificar`, and the notices
  drawing their ring and background after the move to `Notice`. The dossier renders its badges in the
  status slot with the record's own title above them.
- **Measured, not assumed:** the tags screen was the only user of `bg-(--color-surface-2)`, a token
  `styles.css` does not define — 1 of the 9 tokens in use — and the box had no background; the two
  dead form labels (`Quem decide`, `Quem está alterando`) were labels with no field under them, left
  over from before the API took the actor from the session (ADR 0009). Both are gone, and the token
  one is now a gate.
- **What did not move:** the screen count (25), the menu count (16) and the settings tables — no route
  and no setting was added; the data model — no table, no column and no migration; and the API
  contract, whose only change in this range is a Portuguese hint the inbox renders
  (`services/curation_service.py`), which is not part of the document.
- **Not carried, on purpose:** the `words` field of the ban request is still documented in the
  contract as "normalizados ao gravar", the one place the old save verb survives. Changing it
  regenerates `openapi.json` and `schema.d.ts` for a description no screen renders — a decision of
  its own, recorded in the commit that left it.

## 2026-10-09 — the copy pass closes its own gap

- **Range:** `f731d2e..24ba826`
- **Pages:**
  - `guides/curate.md` — **updated**: the page quoted the materialisation panel's button as
    "Conferir o que será feito", and the panel now says **"Conferir impacto"** like every other
    preview in the interface. One line, and it is the report's whole reason for naming the page.
  - `guides/curate.pt.md` — **updated**: the same quote, plus the words the page had carried in
    English all along — `rungs` (nine times) is now **degraus**, `apply` is **aplicação**, and
    `dry-run` is **prévia**. The Portuguese page is the archivist's, and the SPA now names those
    things in Portuguese; a term in English that the interface already names in Portuguese is the
    defect the documenter rule names. The English page keeps `rung` and `apply`: they are the
    project's English words, the ones the API docstrings and `lib/hierarchy.ts` use.
- **Why this round exists:** the previous entry closed the range with the copy pass declared
  complete, and it was not. `components/hierarchy/MaterialisationPanel.tsx` — a component and not a
  screen — kept `rung`, `apply` and `dry-run` through all of it, because the per-screen review never
  opened it and no gate looked. The commit that fixes it also adds the gate
  (`test_curator_copy.py`'s retired-word rule), which is why the page's quoted string is the only
  thing the report could see: the panel is not a `sources:` entry of any page.
- **What did not move:** the screen count (25), the menu count (16), the settings tables and the
  data model — no route, no setting, no table and no migration; and the API contract, untouched by
  this range.
- **Not carried, on purpose:** the retired-word list is deliberately short and its two omissions are
  documented in the test — `gravar` in the sense of *recording*, which is not the `Salvar` action,
  and `desativar`, which is right for an account and wrong for a catalogue row. Neither can be
  decided from the text, and a pattern that guessed would fail on correct prose.
- **The round found a hole in itself, by rendering.** The gate's extractor read a JSX text node only
  up to the first newline, so a sentence the formatter wrapped was read as half a sentence:
  `só o apply absorve as tags`, on the second line of the proposals tab's warning, survived the
  review pass, the sweep and the gate's first version. The rendered screen showed it, the pattern now
  joins a wrapped node, and the extractor's sanity test asserts it does — so the hole is closed by a
  test rather than by a memory. Two states were rendered for this round and are the evidence for it:
  the plan screen's materialisation panel (`Conferir impacto`, `de 81 degraus decididos`, `degraus
  aprovados`, `a aplicação segue o vínculo`) and the tags proposals tab (`incluir no lote de
  aplicação`).


## 2026-10-09 — the shell stops scrolling the menu away, and the footer reaches the public

- **Range:** `24ba826..05819cd`
- **Pages:**
  - `guides/curate.md` — **updated**: a new *The screen is one window tall* states the layout the
    archivist now reads in — the shell is one viewport, only the content column scrolls, the header is
    sticky so the actions stay in reach, and the menu folds into one open section plus the one you are
    standing in, with `Início` standing outside any heading. *The menu collapses to icons* gained the
    one thing the accordion changes about it (collapsed, the accordion is off and all sixteen entries
    show) and the corrected claim about the footer: it renders at the foot of every screen **including
    the three that come before a session**, which was false when it was written.
  - `guides/curate.pt.md` — **updated**: the same two sections, in the SPA's vocabulary.
- **Why the round exists, and what it measured rather than assumed:** the rail used to grow to the
  height of the *page* (`min-h-full`), so on a long screen the whole menu scrolled out of view — at
  1440x900 at the foot of `/entidades/lista`, a blank rail column and no menu at all — and the
  `overflow-y-auto` on the nav never engaged. After the fix, from the DOM: the document is 900px in a
  900px window, the content column 3299px in 867px, and the nav 975px in 734px — which is what proved
  the accordion was still needed. After the accordion, the nav is **734 in 734**: the menu fits, and
  the active group is the one expanded.
- **The footer claim was false and is now true.** `AttributionFooter`'s own docstring says a notice
  hidden behind a login is not a notice to the users of a network service, and the three screens
  before a session returned from `AppShell` before the shell existed — so the four §7(b) elements,
  and the version added in this range, were invisible to anyone without an account. Measured with the
  browser's cookies cleared: `/` now renders all four elements and `v1.0.0`.
- **What did not move:** the screen count (25), the settings tables, the data model and the API
  contract — no route, no setting, no table, no migration and no contract change in this range. The
  menu keeps its **16 entries**; the accordion changed how they are shown, not how many there are.
- **Not carried, on purpose:** the version comes from `pyproject.toml` and not from the API, because
  the built SPA is served by the API from the same commit — so the number is known when the bundle is
  written and a request would buy nothing. The API's own `info.version` is Litestar's default
  (`{"title": "Litestar API", "version": "1.0.0"}`) and was not a candidate.

## 2026-10-09 — one width for every screen

- **Range:** `05819cd..HEAD`
- **Pages:**
  - `guides/curate.md` — **updated**: *The screen is one window tall* gains the width, because the
    width is part of the shell now: the column has **no maximum**, and what keeps a cap is the content
    (a paragraph's measure, a field's width).
  - `guides/curate.pt.md` — **updated**: the same paragraph.
- **Why:** the per-screen caps had drifted — `max-w-5xl` on most screens, `max-w-4xl` on five,
  `max-w-6xl` on one, and four of the dossier's panels carried their own — so on a wide monitor two
  screens stopped growing at different points. That is not a decision, it is drift, and the report of
  it came from looking at the screens side by side. Measured after the change: at 1280 the content
  column is 1024 and the widest child is **1024**; at 1920 both are **1664**, on the four screens that
  used to differ (categories, anomalies, entities and the dossier).
- **What did not move:** the text measure (`max-w-prose`, `max-w-3xl`) and the control widths
  (`max-w-md`, `max-w-xs`, the login forms' `max-w-sm`) — those are decisions about a paragraph and a
  field, not about a screen, and they are the same on every screen. The screen count, the menu count,
  the settings tables, the data model and the API contract are untouched.

## 2026-10-09 — the identity enters the interface

- **Range:** `05819cd..86796d0`
- **Pages:**
  - `guides/curate.md` — **updated**: a new *The identity is on screen* states the rail's navy, the
    logomark in both rail states (and that the cropped mark is the control that expands it), the 2px
    terracotta rule under a screen's header, and the plate on the two cards before a session. It also
    records **why the accent stayed blue**: the terracotta is `oklch(… 31)` and `--color-danger` is
    `oklch(… 25)`, six degrees apart, so a terracotta button and "Excluir" would have been one colour.
  - `guides/curate.pt.md` — **updated**: the same section.
  - `guides/install.md` — **updated**: the first-run card carries the logomark, because it is the
    first screen an installer sees. One sentence, and it is what the report's second page was for.
  - `guides/install.pt.md` — **updated**: the same sentence.
- **Why:** the interface and the logomark shared no colour. Measured before the change: the identity
  is terracotta on navy (`#C4503F` on `#14202B` = `oklch(0.580 0.152 31)` on `oklch(0.238 0.027 247)`)
  and the theme's accent was `oklch(0.52 0.13 250)`, a blue. The navy turned out to share the
  accent's **hue** (247 against 250), which is what let the rail take the identity's dark without
  re-tuning the semantic colours.
- **Verified, rendered:** the rail expanded and collapsed and the sign-in card at 1440x900; the tab
  computes to `oklch(0.58 0.152 31)`, the rail to `oklch(0.238 0.027 247)`, the wordmark to `"PT Serif"`
  at 45px with `document.fonts.check('400 45px "PT Serif"')` true, the header rule to
  `2px oklch(0.58 0.152 31)`, and `/favicon.svg` answers 200 and is in `dist`.
- **What did not move:** the screen count (25), the menu count (16), the settings tables, the data
  model and the API contract — no route, no setting, no table, no migration and no contract change.
  The accent, the danger, the warn and the ok colours are unchanged: the identity's terracotta is a
  brand colour, and the copy gate still holds every string.
- **Not carried, on purpose:** the four identity SVGs stay as design sources under
  `apps/curator/src/assets/brand/` while `Mark`/`Lockup` inline the two shapes the SPA renders. The
  geometry is therefore written twice — a file for the designer and a component for the page — and
  the alternative, generating the components from the files, would put a build step in the middle of a
  logo. `marca-escura.svg` was reconstructed from the family's geometry and is the one file a person
  should look at rather than trust.

## 2026-10-09 — the drawer and the cluster become the words the contract already used

- **Range:** `86796d0..571c6cb`
- **Pages:**
  - `guides/curate.md` — **updated**: `drawer` is **category** (16 times) and the screen is
    `Descobrir Categorias`, which is what the rail says. `cluster` stays: it is the API's own word for
    a proposed grouping (`clusters_found`, `TRIGRAM/PLURAL/MIXED`).
  - `guides/curate.pt.md` — **updated**: `gaveta` is **categoria** (17 times), the same rename.
- **Why:** the interface had its own metaphor for a concept the contract had already named. The API's
  field is `category` — `category_would_be_lost`, `macro_category_name`, `CATEGORY` — and the drawer
  was the interface's word for it, so a reader of both had two names for one thing. Measured before the
  change: **34 visible strings** in the SPA used `gaveta`/`cluster` (Categories 9, Tags 11, Document 7,
  taxonomy 4, Discover 3). None remain, and the gate now holds both words out.
- **The API was split too, and is now aligned:** `hierarchy_requests.py` described a field as
  "Documentação da gaveta para o curador" (a Portuguese `description` in the contract) and two worker
  messages said "formar clusters semânticos". Both say `categoria`/`agrupamentos` now, and the contract
  was regenerated — `openapi.json` and `schema.d.ts` change by exactly that one description.
- **What did not move:** the screen count, the menu count, the settings tables, the data model and the
  API's *shape* — no route, no setting, no table, no migration and no field renamed. The change is a
  word, and the only contract diff is a description's text.
- **Not carried, on purpose:** the **casing of the labels and hints**. The pass over them is half
  applied — some are English-style Title Case ("Lista e Busca", "Facetas e Filtros") and most are
  sentence case ("Onde está incoerente", "A trilha do que foi excluído") — and finishing it one way or
  the other is 25 strings. English-style Title Case applied to Portuguese capitalises verbs
  ("O que **P**recisa de **M**im **H**oje", "Não **É** Assunto"), which the pt-BR convention does not;
  the preview of that direction is in the pull request rather than in this commit.

## 2026-10-10 — the documentation site, published from CI and dressed in the identity

- **Range:** `571c6cb..236bc58`
- **Pages:**
  - `guides/operate.md` — **updated**: the new *The documentation site* section (the deploy path and
    the recovery, ADR 0012), plus the vocabulary the drawer round left behind — `drawer` four times
    and one `gaveta` inside the measurement SQL of an English page. `ci.yml` and `mkdocs.yml` joined
    its `sources:`, so a change to the publish path reports the page stale.
  - `guides/operate.pt.md` — **updated**: the same section, and the same five `gaveta`.
  - `guides/curate.md` — **updated**: the sign-in plate is no longer centred and carries no tagline
    (`bd89df2`, in this range), and the warning still said `"sem gaveta"` in the **canonical** page
    while its own translation said `"sem categoria"`.
  - `guides/curate.pt.md` — **updated**: the identity paragraph, which carried the same "centralizado"
    that stopped being true, in the same sentence.
  - `guides/data-model.md` — **updated**: `drawer` in five places, including the section heading and
    the `archive_macro_categories` row.
  - `guides/data-model.pt.md` — **updated**: the same five, in Portuguese.
- **The report named two pages; the round touched six, and that is the finding.** The freshness report
  is computed from `sources:`, so it can see `LoginForm.tsx` moving under `curate.md` and the worker
  strings moving under `operate.md` — it cannot see a **word** that no source file owns. The previous
  round renamed the concept in `curate.md` and its translation and stopped there: `operate.md`,
  `data-model.md` and both translations still said `drawer`/`gaveta`, and one line of `curate.md` kept
  the old string after the paragraph around it was rewritten. The check that found them was
  `grep -rn "gaveta\|drawer" docs/guides/`, run by hand, and it is worth running after the next
  rename — nothing in the suite would have failed.
- **A correction in the ledger itself, in this diff.** The entry above ended its range at `HEAD`,
  which `_RANGE` cannot parse, so `ledger_floor` fell back to the range before it and the report
  re-flagged pages that round had already triaged. It now names the commit it meant (`571c6cb`), and
  this entry starts where it ends.
- **The gate this change adds, and why it is a test.** `mkdocs build --strict` exits 0 when
  `theme.logo`, `theme.favicon` and `extra_css` all point at files that do not exist — measured, not
  assumed. `testing/unit/docs/test_docs_brand.py` therefore pins the wiring (an asset named and not
  present fails), the copies (byte for byte against `apps/curator/`, so the identity cannot drift),
  the palette (against the tokens of `apps/curator/src/styles.css`, read out of that file rather than
  repeated) and the `url(...)` the stylesheet reaches for.
- **Not carried, on purpose:** `guides/install.md`, `index.md` and the guides not named above —
  nothing in the range touches what they document, and `adr/` is not a sourced surface (ADR 0010).

## 2026-10-10 — the worker settings leave the operations panel (issue #53)

- **Range:** `236bc58..89e6a43`
- **Pages:**
  - `guides/curate.md` — **updated**: a new *Configuração dos Workers — `/configuracoes/workers`*, and
    *Workers de IA* reduced to the machine view — the queue and running one now — with the effective
    configuration explicitly **read only**. The Configurações table and the *Operação* card row gain
    the fourth screen.
  - `guides/curate.pt.md` — **updated**: the same two sections, in the SPA's vocabulary.
  - `guides/operate.md` — **updated**: `GET /api/v1/system/workers/settings` joins the route table,
    the SPA table gains `/configuracoes/workers`, and the polling paragraph says why the new read
    exists — it resolves the same configuration and counts no queue. The `ci.yml` change of `41fffc7`
    (dropping `configure-pages`) is **no-change** here: the page describes the artifact and the deploy
    job and never named the dropped step.
  - `guides/operate.pt.md` — **updated**: the same two tables and the same paragraph.
- **Why the round exists:** issue #53 split a screen that answered two questions — what the machine is
  doing and what the installation is *set* to do. The API gained exactly one read
  (`WorkerOperationsService.list_settings`, over the same `_resolved_workers` traversal the panel
  uses) because the panel's `GET /system/workers` counts nine queues and the configuration screen
  shows none of them. The precedence (`explicit argument > the archive_worker_settings row > the
  signature default`) and the refusal of `config` as an option are unchanged; the split moved where
  the write is made, never what it means.
- **What did not move:** the data model and the migrations — no table, no column, no migration and no
  settings field. `packages/api-contract/openapi.json` and `schema.d.ts` move by exactly one route and
  its two schemas (`SystemWorkerSettingsResponse`, `WorkerSettingsItemDTO`).
- **Verified, rendered:** the built SPA served by the API on a migrated throwaway database, looked at
  with the headless shell. `/configuracoes/workers` renders its heading and the nine cards (each with
  `padrão do código` and the effective engine/preset/config), and expanding the NER card shows the
  Engine and Preset selects, the batch field, the JSON options field and *Salvar padrão* / *Voltar ao
  padrão do código*, with no runtime exception. `/sistema/workers` renders the same nine rows with
  **only** *Rodar agora* — no *Configurar* — and the engine and preset still on the collapsed row. The
  throwaway database's schema was dropped and the server stopped after the check.
- **Not carried, on purpose:** `guides/install.md`, `index.md` and `guides/data-model.md` — the round
  adds no setting field, no table and no install step, and install's sources did not move.

## 2026-10-10 — the pre-release pass for 1.1.0

- **Range:** `89e6a43..b291d36`
- **Pages:**
  - `guides/install.md` — **no-change**: the round moves the version in `pyproject.toml` and the
    curator's `package.json`, and this page documents the versions of the **tools** (Docker, `uv`,
    Bun, Python) and the settings — never the release the checkout is on. Nothing it states stopped
    being true: the version an installation runs is read from `pyproject.toml` at build time and
    shown in the page footer, not written into this page.
- **Why the round exists:** milestone 1.1 closed, so this is the release preparation the release
  section of `CONTRIBUTING.md` asks for in one pull request — the version, the changelog, and the
  claims that had drifted while no gate looked at them.
- **What the report cannot see, and what found it.** The freshness report is computed from
  `sources:`, so it saw `pyproject.toml` move under `install.md`; it cannot see a page with no
  `sources:` (`README.md`, `docs/index.md`) and it cannot see a **number** inside a page whose
  sources did not move. The three that were wrong came from reading the claims against the code:
  the README's screen table listed 24 of the 26 routes of `router.tsx` and its status line still
  said `1.0.0`; `guides/curate.md` said **25** screens where `router.tsx`, `ScreenId` and `SCREENS`
  all carry **26** (measured: the three sets are equal, and issue #53 added the twenty-sixth while
  the round that landed it recorded the count as unchanged); the documentation index said
  "Scrinalia is at 1.0". The fourth came from the check the ledger of the rename round asked for:
  `grep -rn "gaveta\|drawer" README.md docs/guides/` — the README still said `drawer` five times
  (the subject-axis paragraph and two screen rows) because that round swept the guides and stopped
  there. It is the second time the same rename was finished page by page, and the reason is the
  same: `drawer` is a word, and no `sources:` list owns a word.
- **The one number the release moved that no page owned.** `info.version` was Litestar's
  `DEFAULT_OPENAPI_CONFIG` — `title="Litestar API"`, `version="1.0.0"` — because `create_app()`
  never passed an `openapi_config`; measured with the project already at 1.1.0, the served
  configuration was unchanged. `api/openapi.py` now derives both from the project, and
  `testing/unit/api/test_openapi_metadata.py` fails when the served document, the installed
  distribution, `pyproject.toml` and the committed `openapi.json` disagree. `guides/curate.md` is
  the page that declares the contract as a source, and it was touched in this round for the screen
  count, so the report stayed quiet — correctly: the route delta was empty, because the change adds
  no route and removes none.
- **Not carried, on purpose:** the ADRs. `0010` still records "24 screens in `router.tsx`" as the
  measurement it was ratified against, and `0012` still quotes the index's old "at 1.0" as the
  example of a claim about a release. An ADR records the reasoning at the time, and neither number
  is a rule the code has to satisfy. `cluster` also stays, in the README's Discover row and in the
  guide: it is the API's own word for a proposed grouping (`clusters_found`,
  `TRIGRAM/PLURAL/MIXED`), which is the distinction the rename round drew and this one keeps.

## 2026-10-10 — the collection pagination

- **Range:** `b291d36..b99408e`
- **Pages:**
  - `guides/curate.md` — **no-change**: the *Lista e busca — `/acervo/lista`* section says "the URL is
    the state, so a filtered list is shareable and the back button works", lists the facets and
    states that nothing is written. It never describes the page buttons, and the fix makes "Próxima"
    obey the sentence that was already there — a screen changed one expression, not a decision.
  - `guides/operate.md` — **no-change**: the `/sistema/execucoes` row describes the ledger, the
    failures of the last 30 days grouped by root cause and the click that filters the ledger to its
    occurrences; it never states how the ledger pages. The expression that moved keeps the page a
    caller sends and returns to the first page for a filter, which is what the row already implies.
- **Why the round exists:** the freshness report named both pages after `e89bfbb`/`b99408e` touched
  four route files. Two `no-change` verdicts are the honest outcome here: a defect that stopped a
  documented behaviour from happening is repaired in the code, and a page does not change because the
  code started keeping a promise the page already made.
- **What the round measured.** `/acervo/lista` builds its request from the URL (`CollectionRoute.tsx`,
  `toRequest`), so the page's claim was true of the read and false of the two buttons; the gate that
  keeps it true is `testing/unit/curator/test_curator_search_state.py`, which fails on an object that
  spreads `changes` and then writes a literal `offset`. The three other screens with the same fold
  (`DeletionsRoute`, `SystemRunsRoute`, `DiagnosticsRoute`) are normalized in the same change.

## 2026-10-12 — the entity merge and the normalized identity

- **Range:** `b99408e..c1a6fbf`
- **Pages:**
  - `guides/curate.md` — **updated**: the *Entidades — `/entidades/lista`* section justified the pair
    list's two ids with "two rows can read the same name". That sentence described the defect: case
    twins scored 1.000 on the trigram scan (`#1167 A. B. Deter ≈ #92610 a. b. deter`). The migration
    reconciles them, so no two entity rows share a normalized name any more and the reason now reads
    "almost the same name" — the similarity list is about spellings that are close, not identical.
  - `guides/data-model.md` — **updated**: the *Subjects, categories and entities* table marks
    `archive_tags.name` and `archive_entities.name` as unique, which is still true, and said nothing
    about the identity rule the schema now enforces. One paragraph states it: `lower(btrim(name))` is
    unique on both tables next to the unique `name`, and the insert path normalizes the spelling
    before it looks an existing id up.
- **Why the round exists:** the freshness report named both pages after `eae9943` and `c1a6fbf`, the
  two commits of issue #68 — the shared synonym upsert and the reconciliation migration.
- **What the round measured.** The migration was replayed on a `pg_dump` copy of the reference
  collection before it touched the collection: 8 322 entities with 3 523 twin groups and 82 317
  links became 4 799 entities with 0 twin groups, 0 non-normalized names and 64 504 links — exactly
  the number of distinct `(description_id, survivor)` pairs computed before the run, with the 266
  synonyms intact and none dangling and the surviving ids equal to the predicted ones. The upgrade
  then ran on the collection itself and measured the same numbers, and `alembic check` reports no
  drift on both. Not looked at in a browser: the evidence is the integration tests (the merge of the
  issue's cluster, the dedup on both axes, the index rejecting a case twin), `basedpyright` and that
  measurement.


## 2026-10-12 — the tag decision queue and the category expansion

- **Range:** `c1a6fbf..820f3c9`
- **Pages:**
  - `guides/curate.md` — **updated**: the *Tags* route had four tabs and the page said so ("One route,
    four questions"). The fifth, **Classificar**, is the subject decision itself, so the page gains a
    subsection for it: the `GET /tags/catalog` read and its `subject_state` partition, the three
    destinations of one tag (`PATCH` into a category, `PATCH` with `null`, `PUT`/`DELETE` on the
    facet), the durability of "not a subject" through `domain_subject_exclusions`, and the fact that
    the selection writes the same three. The *Categorias* section gains the expansion it never had:
    the two tabs of a card, the list read through `macro_category_id` with the badge and the `total`
    being one definition, and the read-only preview with its `Editar`. The summary table's two rows
    name the new decisions.
  - `guides/data-model.md` — **updated**: the facet paragraph said "nothing writes a facet
    automatically" and named no writer, which was true and incomplete — the table had none at all.
    One clause now names the act (`PUT /tags/{id}/facets/{facet_type}`, undone by `DELETE`) and the
    two things it settles with it: the drawer it empties and the subject exclusion it registers.
  - `guides/install.md` — **no-change**: its only source in the range is `SetupForm.tsx`, and the
    paragraph that describes it says the first-run card carries the logomark at the top "on the same
    plate the sign-in card has". The commit made the two plates identical — it dropped the tagline the
    sign-in card had already dropped and moved the padding inside the card — so the sentence became
    truer, not staler. Nothing the page states about the setup flow, the routes or the closing of both
    doors moved.
  - `guides/operate.md` — **no-change**: `e2ecd04` memoizes the once-only log sink (the page describes
    what is written, not how the sink is held), `4ff8144` reads the URL alphabet of `worker_ner` from
    the RFC (the page documents the panel and the ledger, never the character classes), `bc7fc07` only
    gives the port stubs a body that has an effect, and from #64 the page's sources gained
    `TagCatalogState` in `models/enums.py` and one `validateSearch` in `router.tsx` — a subject-axis
    filter and an SPA route, neither of which the operations panel reads.
- **Why the round exists:** the freshness report named four pages after 30 commits landed on `dev`
  since the last entry, three of them the work of issues #64 and #65, and it printed the three new
  operations (`GET /tags/catalog`, `PUT`/`DELETE /tags/{id}/facets/{facet_type}`) beside
  `guides/curate.md`.
- **What the round measured on the collection.** On the reference collection (`memoriacuritibana`:
  8 103 tags, 55 345 links, 5 subject exclusions, 0 facets) the partition holds and the numbers are
  those of the change: `PENDING` 7 407 + `NOT_SUBJECT` 3 + `FACET` 0 = 7 410, exactly the tags with
  `macro_category_id IS NULL` that the card used to count. So the card's number barely moves *today* —
  what the change makes reachable is the other 7 407, which had no screen and no durable write. The new
  predicate costs 4.43 ms against the old column's 0.87 ms (both a sequential scan of 8 103 rows; the
  two `NOT EXISTS` read a 0-row table and a 5-row one), and the catalogue's first page — the page, its
  total aside — plans and executes in 19.6 ms with `limit 25` over the grouped link count. Neither is a
  home-screen cost.
- **What the round looked at.** The two screens were **looked at**, not inferred: the built SPA was
  rendered with the dev stack (Vite on `:5173`, the API on the zeroed database) through the headless
  shell, with scratch rows seeded into that database — 7 tags, 40 descriptions, 79 links, one facet and
  two exclusions — and removed again afterwards, because a zeroed collection shows no row to judge.
  That found one defect no gate could see: the batch bar's drawer select inherited the bar's white text
  on its own white background, so its placeholder rendered invisible. Measured with `getComputedStyle`:
  `color` and `background-color` were both `rgb(255, 255, 255)` before the fix and `oklch(0.24 0.012 60)`
  on white after it. The rest of what the pixels confirmed: `PENDING` listed 4 tags with the classifier's
  confidence beside each, `FACET` listed `rua exemplo` with the *Lugar* badge and its "tirar de lugar"
  button, the category card's badge said 12 descrições while the list answered "1–10 de 12", the
  read-only panel showed the title, both badges, the ISAD(G) fields and every tag with its category, and
  the card's `Editar` tab rendered the form with `Salvar` disabled while nothing was dirty. **Not**
  verified: the collection's own screens. The API was pointed at the zeroed database, so the pixels are
  of a seeded scratch collection, not of `memoriacuritibana`; what was measured there was the SQL, read
  through `psql`, not the screen.

## 2026-10-12 — the review of the decision queue (no page changed)

- **Range:** `820f3c9..b759393`
- **Pages:**
  - `guides/curate.md` — **no-change**: the range *is* the review of the change the previous entry
    documented. The offset clamp answers 200 where the route answered 500 (`offset=-1`), the contract
    pair moved only in the docstring of `TagCatalogState`, and the four curator fixes changed the
    search box's debounce guard, the counts rendered while `placeholderData` held the previous filter,
    the row's select (retired categories now included and marked) and the batch's report of what it
    wrote and what did not answer. No sentence of the page described any of those behaviours as they
    were — and the page already said the batch "reports how many tags it wrote and where", which the
    fix made true for the failure case too.
- **Why the round exists:** the two `fix` commits landed *after* the documentation commit, which is
  exactly the signal the report is for: a page whose sources moved is a candidate, and a candidate is
  closed with a reason rather than an edit.

## 2026-10-13 — the collision batch

- **Range:** `b759393..0fd528e`
- **Pages:**
  - `guides/curate.md` — **updated**: the collisions screen gained the category filter (`entity_type`,
    the same read the batch selects with) and the batch itself,
    `POST /api/v1/taxonomy/conflicts/resolve/batch`. A new subsection, *Deciding a category at once*,
    says what the unit of the write is (the pair, never the selection), why `skipped` is not `failed`,
    and why `remaining` is the same read taken twice. The `Pendentes` bullet now names the filter, and
    the summary table's row says the decision covers one pair or a whole category, with one ledger row
    per pair.
- **Why the round exists:** the freshness report named one page after the two commits landed on the
  branch — the API route and the SPA screen — and printed the one new operation,
  `POST /api/v1/taxonomy/conflicts/resolve/batch`, beside `guides/curate.md`. The range also carries
  three commits no earlier entry had closed (`1f28807`, `7012898`, `e745466`); the report named no page
  for them, so they are closed here by absence.
- **What the round looked at.** The screen was **looked at**, not inferred: the built SPA was served by
  the API against the zeroed collection with a scratch account (created for the round, deleted after),
  and the headless shell rendered the route. Measured in the pixels: the category row (`todas as
  categorias` / `Local` / `Pessoa` / `Organização`) with `nomes idênticos` selected; the batch card
  reading "80 par(es) · nomes idênticos"; and the panel opening on a click, with the note field and
  the two verdict buttons. With `?tipo=exact_name&categoria=LOC` the header, the card and the list move
  together — 36 collisions, all `Local` — which is the selection the batch writes. **Not** verified in
  pixels: the write itself. Resolving a category from the screen would have destroyed 36 pairs of the
  working collection, so the write is verified by the integration suite, which drives the real route
  and the real ledger (814 integration tests passed); the screenshots show the selection and the
  panel, not a resolution.

## 2026-10-13 — the entity merge ledger (issue #34)

- **Range:** `0fd528e..318f8e0`
- **Pages:**
  - `guides/curate.md` — **updated**: the *Mesclar* bullet of *Entidades — `/entidades/lista`* said
    entities had "no proposal catalogue and no ledger", so there was no undo and no preview route.
    It now names the preview (`POST /api/v1/taxonomy/entities/merge/preview`, the plan the write
    executes), the ledger (`GET /api/v1/taxonomy/entities/merge-log`, one row per absorbed entity)
    and the undo (`DELETE /api/v1/taxonomy/entities/merge-log/{merge_id}`), and the summary table's
    row says the merge is reversible. The entity merge also **left** the *What has no way back*
    warning: it is no longer one of the writes that announce they have no undo.
  - `guides/data-model.md` — **updated**: the subjects-and-entities table gained the
    `archive_entity_merge_log` row — one row per absorbed entity, snapshotted before anything
    changes, and what `undo_entity_merge` restores from it.
- **Why the round exists:** the freshness report named both pages after the two code commits landed
  on the branch (the API and the SPA screen) and printed the three new operations beside
  `guides/curate.md`: `POST /entities/merge/preview`, `GET /entities/merge-log` and
  `DELETE /entities/merge-log/{merge_id}`. The range also carries `a63b6c9` and `402d657` (the
  collision batch's documentation and API commits), which no earlier entry closed; the report named
  no page for them, so they are closed here by absence.
- **What the round measured.** The write and its reverse are pinned by the integration suite, which
  drives the real repository and the real ledger: the undo restores the row, the per-entity links and
  the spelling state exactly, removes only the links the merge created (`created_link_ids`) and puts
  back the canonical name the optional rename changed; the preview and the apply are asserted to
  produce the same numbers; and the `pair_kind` partition of the conflict routes, which this change
  must not disturb, keeps its own tests green. Measured: 1 511 tests passed, `basedpyright` 0 errors,
  `alembic check` reports no drift after the new table.
- **What the round looked at.** The screen was **rendered**, not inferred: the built SPA was served by
  the API (`create_app()` mounts `apps/curator/dist`) against the reference collection, with a scratch
  session created for the round and deleted after, and the headless shell drove `/entidades/lista` over
  CDP. Seen in the pixels: the list with the new sentence ("mesclar tem desfazer: cada entidade
  absorvida entra no ledger antes de a escrita acontecer"); the merge panel opened by marking two rows,
  reading "33 descrição(ões) passam a carregar **smu** · 33 vínculo(s) reescrito(s) · 1 entidade(s)
  absorvida(s)" — the planner's real numbers over the real collection, not a copy — with the updated
  warning below it; and the new *Ledger dos merges de entidades* section at the bottom, with its
  server-side search box and the empty state ("Nenhum merge aplicado ainda"). **Not** verified in
  pixels: a merge actually written and undone from the screen. Applying one would have written to the
  reference collection's ledger, so the write rests on the integration suite, which drives the real
  repository and the real ledger.

## 2026-10-13 — an entity opens into its descriptions (issue #86)

- **Range:** `08500a9..HEAD`
- **Pages:**
  - `guides/curate.md` — **updated**: *Entidades — `/entidades/lista`* gained the read half of the
    screen, which it never described. A name expands into the **descriptions that carry it**
    (`GET /api/v1/documents` with the new `entity_id` filter, paged ten at a time inside the card);
    the badge above and the list's `total` are one number counted twice, pinned by
    `testing/integration/api/controller/test_entity_documents.py`; a row opens the read-only preview
    the category screen already uses, and its "Editar" lands on the dossier's **Assuntos** tab, which
    is where a description's entities are added and removed. `?aberta=`, `?offset=` and `?descricao=`
    are named as the state the URL carries.
  - `guides/curate.pt.md` — **updated**: the translation of the same paragraph.
- **Why the round exists:** the section listed the screen's decisions and said nothing about reading
  it, while the card promised "3.152 descrições" and the screen had no way to show which ones. The
  freshness report named `guides/curate.md` for the SPA and API commits of this change.
- **What the round measured.** The pairing was measured on the **reference collection**, through the
  routes the screen calls and not against a fixture: `entity_id=10` (*Curitiba*) answers
  `total=3152` where the card shows `total_usage=3152`, and `2679`/`2670` answer `2467` against
  `2467`. Measured: 1 513 tests passed, `basedpyright` 0 errors, `alembic check` reports no drift (the
  change adds no migration), and the SPA's `tsc`, ESLint and Vite build are green. The new test seeds
  one description carrying **two** entities on purpose, so the join it forbids would answer 2 where
  the card promises 1 — the same trap `test_category_documents.py` pins for the drawers.
- **Found and deliberately not fixed.** `EntityRepository.get_relevance_count` **inner-joins** the
  link table, so the ranking never lists an entity that no description carries: `EntityRow`'s orphan
  branch, and the per-row *Excluir* button with it, is unreachable from the Relevância tab. That is a
  separate defect about a separate decision (whether the ranking should left-join and list orphans at
  zero), so it was left alone and pinned as measured in
  `test_an_orphan_is_not_ranked_and_its_expansion_is_empty`.
- **What the round looked at.** The screen was **rendered**, not inferred: the built SPA served by the
  API (`create_app()` mounts `apps/curator/dist`) against the reference collection, with a scratch
  session created for the round and deleted after, and the headless shell driven over CDP. Seen in the
  pixels: `/entidades/lista?aberta=10` with the *Curitiba* card open, the badge "3.152 descrições"
  above the expansion's own "1–10 de 3.152", the controls (checkbox, `tipo`, *Excluir*) outside the
  toggle and the name and badges inside it — which is the click that used to mean two things; the
  preview panel over the list, rendering the shared `DescriptionPreview`; and
  `/assuntos/categorias?aberta=4` still rendering its own expansion after the component was lifted out
  of `CategoriesRoute.tsx` ("2.312 descrições" against "1–10 de 2.312"). Read from the DOM and not
  inferred: the entity panel's *Editar* carries `href="/acervo/53617?aba=assuntos"`, and the category
  panel's still carries `?aba=descricao`. **Not** verified in pixels: the empty expansion ("Nenhuma
  descrição carrega este nome"), unreachable from this screen for the reason above, and any write —
  the round only read.

## 2026-10-13 — renaming a name, with an undo (issue #85)

- **Range:** `6c79880..HEAD`
- **Pages:**
  - `guides/curate.md` — **updated**: *Entidades — `/entidades/lista`* gained its fourth decision,
    **Renomear** (`PATCH /api/v1/taxonomy/entities/{entity_id}`), with the three facts the screen has
    to state: the previous spelling stays anchored as a synonym unless `keep_old_synonym` is turned
    off, the write leaves one `RENAME` row in the merge's own ledger so the ledger's "desfazer"
    reverses it, and a spelling another entity already carries is a **409** that names the twin and
    points at the merge. The summary table's row now says the rename is reversible, and the read
    paragraph names the card's second tab, which is where the rename lives.
  - `guides/curate.pt.md` — **updated**: the translation of the same.
  - `guides/data-model.md` — **updated**: the `archive_entity_merge_log` row now says the table holds
    a **merge** (one row per absorbed entity) or a **rename** (one per name), and names `kind` as the
    checked discriminator the undo branches on.
  - `guides/data-model.pt.md` — **updated**: the translation of the same.
- **Why the round exists:** the name was the one field of the entity vocabulary with no write of its
  own. The rename already existed in the repository and the service — with a test, and shared with the
  merge's optional rename — but no route reached it, and the screen's only rename field lived *inside*
  the merge panel, so a plain typo had no path that did not absorb another entity. The freshness
  report named `guides/curate.md` for the API and SPA commits of this change.
- **What the round measured.** Measured: 1 524 tests passed, `basedpyright` 0 errors, and the
  migration applied, reversed and re-applied on the reference database with `alembic check` reporting
  no drift. The write and its reverse are pinned by the integration suite against the real repository:
  the rename leaves exactly one `RENAME` row (no absorbed entity, no links), the undo restores the
  name and drops the spelling the rename planted, `keep_old_synonym=False` writes no spelling at all,
  the collision raises `DuplicateEntityNameError` with the twin in `details` **before** the write, and
  a **merge with a rename leaves one row per absorbed entity and no `RENAME` row** — the trap the
  shared writer would otherwise have created. `refusalMessage` is what turns that payload into the
  sentence, so the copy the archivist reads is the interface's, not the server's.
- **What the round looked at.** The screen was **rendered** against the reference collection
  (`scrinalia_zeroed`, the ~100-description collection, already at head): the built SPA served by the
  API, a scratch session created for the round and deleted after, and the headless shell driven over
  CDP. Seen in the pixels: `/entidades/lista` with the row's **Renomear** in `actions`, outside the
  toggle, and the card opened by it on the **Editar** tab, with the name input and the "manter a
  grafia antiga como sinônimo" box checked; the same form refusing `curitiba` with "Já existe uma
  entidade chamada \"curitiba\". Mescle as duas em vez de renomear." and the request reference, with
  the row still reading `paço da liberdade` — the refusal happened before the write; and the ledger
  card, reading **"paço da liberdade → paço da liberdade de curitiba · renomeação · 13/10/2026, 15:21
  · por Cassio"**, which is the rename applied through the route on that collection. The **desfazer**
  was then clicked *on the screen*, and the ledger row came back as "desfeito em 13/10/2026, 15:23"
  with the row reading `paço da liberdade` again; read back from the database, the entity carries its
  original name and no spelling row survives, which is the undo doing its job rather than the screen
  redrawing. The round's own artifacts were then removed — the scratch session and the ledger row it
  left — so the collection is as it was and no test write remains in its audit trail.

## 2026-10-13 — the merge card fed by the type-ahead (issue #87)

- **Range:** `e0c0720..bbd0189`
- **Pages:**
  - `guides/curate.md` — **updated**: *Entidades — `/entidades/lista`* now says the merge has **three
    doors** — the selection on Relevância, a pair on Similaridade and the **Mesclar pelo nome** card
    above the tabs — and why the third exists: the other two are list-driven, relevance is ordered by
    weight and capped, and similarity is trigram, the one measure that fails on the pair the archivist
    is most sure about. It names the card's three decisions: the type-ahead with the API's own
    two-character floor, each name's weight shown so the canonical is chosen with the numbers in view,
    and a list of its own that does not consume the relevance checkboxes.
  - `guides/curate.pt.md` — **updated**: the translation of the same.
- **Why the round exists:** the screen had two ways into the merge panel and the archivist controls
  neither list, so the pair they already know is one entity was the pair the screen was least likely
  to show them. The freshness report named `guides/curate.md` for the SPA commit.
- **What the round measured.** Measured: 1 528 tests passed, `basedpyright` 0 errors, the SPA's `tsc`,
  ESLint and Vite build green, and `mkdocs build --strict` clean. The acceptance pair was measured
  against the reference collection before it was rendered: `smu` (entity 45) carries **68**
  descriptions and `smcs secretaria municipal de comunicação social` (entity 349) carries **1**, so the
  relevance ranking — capped at fifty rows, whose lightest entry carries two — can never show both;
  and `similarity('smu', 'smcs secretaria municipal de comunicação social')` is **0.045**, far under
  any threshold the similarity tab accepts. Neither list reaches the pair; the card does.
  `testing/unit/curator/test_entities_merge_doors.py` is the gate for the shape: it fails when the
  write gains a second call site, when a door stops rendering `<MergePanel`, or when the card starts
  calling the write, the preview or `navigate` itself. It is a **textual** gate and says so — the SPA
  has no test runner of its own.
- **What the round looked at.** The screen was **rendered** against the reference collection: the
  built SPA served by the API, a scratch session created for the round and deleted after, the headless
  shell driven over CDP. Seen in the pixels: the card **collapsed** between the irreversibility
  `Notice` and the tabs, with the labelled "+ Mesclar pelo nome" button; and the card **open** after
  the two names were typed and picked one at a time, each row carrying its own weight ("smu · Local ·
  68 descrições", "smcs secretaria municipal de comunicação social · Local · 1 descrição"), with the
  panel below stating the **real** plan — "1 descrição(ões) passam a carregar smu · 1 vínculo(s)
  reescrito(s) · 1 entidade(s) absorvida(s)" — and its warning once, not twice. **Not** verified in
  pixels: an actual merge from this card. The round wrote nothing to the collection, and the write
  itself rests on the suite that pins the three doors to the one call site.

## 2026-10-13 — the SPA stops re-declaring the contract's query shapes (no page changed)

- **Range:** `e0c0720..HEAD`
- **Pages:** **none**, and that is the verdict this entry records. The change lives inside
  `apps/curator/src/api/`, and no page declares that path among its `sources:` — the freshness report
  named no page for it. What changed is a **rule file**,
  `.dsh/skills/curator-ui/SKILL.md`: it now states that a query shape is derived from the route and
  never typed out, with the measured failure beside it.
- **Why the round exists:** the last change to this surface (#86) added `entity_id` to the contract and
  had to add it to the hand-written mirror by hand. Sizing that mirror found it had **already** lost a
  field, and that seventeen more shapes shared the pattern. A convention with no gate is what principle V
  is about, so the round closed the convention and left a test that fails on the next one.
- **What the round measured.** `DocumentSearch` declared **14** keys against the route's **15**, missing
  `is_anomaly`, and nothing failed: `CollectionRoute.toRequest` spreads a wider `CollectionSearch` into
  it, the extra key survives the return type, and `openapi-fetch` sent it — so the screen filtered
  correctly through a field its own type denied. What that was hiding, measured with a session against
  the reference collection: `GET /api/v1/documents?is_anomaly=true` answers **28**, `?is_anomaly=false`
  **73** (28 + 73 = 101, the whole collection), and a misspelled `?is_anomalyy=true` or a nonsense
  `?non_sense=42` answers **101 with HTTP 200 and no warning** — an unknown query parameter is ignored,
  not refused. A contract that renamed the filter would therefore have left the list unfiltered with a
  chip on the screen saying it was filtered, and `tsc`, ESLint, the build and the suite green.
  **19** shapes derive from their route now (three of them named), and the ten call sites that build a
  one-key value inline — `query: { only_active: true }`, `query: { term, limit }` — are measured and left
  alone: they are values, not declared shapes, and deriving them would change the client's own signature
  and every caller. Measured: 1 528 tests passed (four of them the new gate), `tsc`, ESLint and the Vite
  build green. The derivation needed **no** reinterpretation — the generated type already spells an
  omitted filter `campo?: T | null` — and an earlier `Exclude<T[K], null>` mapping was measured to be
  both unnecessary and wrong (it rejected two callers that legitimately hold `null`).
- **What the round looked at.** The screen was **rendered**: `/acervo/lista?is_anomaly=true` against the
  reference collection, with a scratch session created for the round and deleted after, the headless
  shell driven over CDP. Seen in the pixels: the header reading **"28 descrições"** with the chip
  **"Somente anomalias ✕"** and every row carrying its `anomalia` badge — the same 28 the route answers,
  now filtering through a field the type declares instead of one it denied.

## 2026-10-13 — the stopword purge stops being the write with no way back (#36)

- **Range:** `f0ba7c2..HEAD`
- **Pages:**
  - `guides/curate.md` — updated (the purge moved out of "what has no way back", the Stopwords
    section describes the ledger and the undo, and the reversibility table says yes)
  - `guides/curate.pt.md` — updated (the translation of the same three passages)
  - `guides/data-model.md` — updated (`archive_stopword_purge_log` joined the ledger table and the
    list of tables that carry an author pair)
  - `.dsh/skills/taxonomy/SKILL.md` — updated (the rule file said the purge "has no undo"; it now
    states the plan/apply/undo, the `synonym_names` snapshot and the ban that the undo must not lift)
- **Why the round exists:** the decision on #36 was a ledger, scoped to destructive writes — and the
  page had been describing the exception as if it were the rule. The docs were not stale by drift;
  they were stale because the decision changed what is true.
- **What the round measured.** The round trip through the routes, against `scrinalia_zeroed`: a
  scratch tag `1924` carrying **2** documents, `POST /tags/stopwords/purge/preview` answering
  `reversible=true, total_tags=1, total_documents=2`, the purge answering `tags_deleted=1,
  purge_ids=[1]`, and `DELETE /tags/stopwords/purge-log/1` putting the row and both links back while
  `domain_stopwords` kept `1924 | TAG`. The scratch tag, the ledger row and the scratch session were
  deleted after the round. Measured: **1540** tests passed, `ruff check`/`format --check` and
  `basedpyright` (0 errors) green, `alembic check` reporting no drift, the contract regenerated and
  stable, and `tsc`, ESLint and the Vite build green.
- **What the round looked at.** The screen was **rendered**: `/assuntos/tags?aba=stopwords` with the
  scratch session, the headless shell driven over CDP. Seen in the pixels: the notice reading
  **"Como o merge, ela guarda um ledger"**, the card **"Ledger das purgas"** with the row
  **"1924 · 2 doc(s) · por Cassio"** and its **desfazer** button, and — after clicking it — the same
  row showing **"restaurada em 13/10/2026, 18:13"**. **Not** looked at: a purge over a real
  stopword of the collection (none of the 88 matched a tag, which is why the scratch tag existed).

## 2026-10-13 — the API enforces the temporary password (#79)

- **Range:** `bbd0189..feed903`
- **Pages:**
  - `guides/curate.md` — updated (the sign-in section now says the API refuses every operation but
    the change, and names the three it still reaches, instead of leaving the refusal to the shell)
  - `guides/curate.pt.md` — updated (the translation of the same paragraph)
- **Why the round exists:** the section described the temporary password as the screen's promise —
  "the account replaces it at the next sign-in" — while the guard read nothing, so a script holding
  the password the CLI printed kept the account's whole role. The decision that the **API**, not the
  screen, owns the refusal changed what is true on a page that documents the guard
  (`src/scrinalia/api/security.py` is in its `sources:`), which is why this is a `updated` and not a
  `no-change`.
- **What the round measured.** The route through HTTP, against the test database: an account with
  `must_change_password=True` signed in, `GET /api/v1/curation/inbox` answering **403** with
  `error_code: "PasswordChangeRequiredException"` and `code: "PASSWORD_CHANGE_REQUIRED"`,
  `GET /auth/me` and `POST /auth/logout` answering **200**, and the same inbox answering **200**
  after `POST /auth/password`. Before the fix the same inbox answered **200** with the flag set —
  the defect, measured in this checkout before the guard changed. Measured: **1550** tests passed,
  `ruff check`/`format --check` and `basedpyright` (0 errors) green, and the contract regenerated
  with one additive enum member (`PASSWORD_CHANGE_REQUIRED`) and the committed client rebuilt from it.
- **What the round looked at.** No screen was **rendered**, and none needed to be: no SPA file
  changed, the forced screen already reads the flag from `/auth/me` and calls `/auth/password`, and
  this change moves the enforcement behind that screen. **Not** looked at in a browser; the evidence
  is the integration test over HTTP, the unit guard test and the regenerated contract.

## 2026-10-13 — the scrape and the transform can be bounded per run (#47, #48)

- **Range:** `feed903..84bb5f0`
- **Pages:**
  - `guides/operate.md` — updated (the pipeline table said "Nine workers, in pipeline order" and
    started at `transfer`; the page now names the two stages in front of it and documents their host
    commands, their flags, how a bounded run resumes by itself, and that a forced one resumes only
    with `--after`)
  - `guides/operate.pt.md` — updated (the translation of the same two pieces)
  - `guides/install.md` — updated (`ACERVO_SOURCE` also selects the origin's ports now, and
    `--origin` overrides it for one run, which is that row's business)
  - `guides/install.pt.md` — updated (the translation of that row)
- **Why the round exists:** the report named `guides/install.md`, whose `sources:` include
  `ingestion/sources.py`, because that module gained the origin's port registry. `operate.md` was
  **not** reported stale — it declared neither ingestion nor staging — and that was the gap: the two
  stages that produce everything the archive reads had no page, and this change turns them into a
  batched operation an operator has to be able to run.
- **What the round measured.** Full suite **1574 passed** (`uv run pytest`, with
  `TEST_DATABASE_URL` pointed at the test database on 5434), `ruff check` and `ruff format --check`
  green, `basedpyright` **0 errors**, `alembic check` reporting no new upgrade operations (no schema
  change), `mkdocs build --strict` green.
  The batched run was measured on a **throwaway database** — created on the test server, migrated
  with `alembic upgrade head`, seeded through the repositories and dropped afterwards — because the
  reference collection cannot reproduce the issue's "queue of thousands": measured there,
  `scraping_queue` holds **100** rows, all `DONE`, with **100** `raw_data`, **100**
  `staging_documents` and **101** `archive_documents`, and **nothing pending to transform**. On the
  scratch database, with a 250-row queue and a port double in place of the site: `--limit 100` took
  **100** and left **150**, then **100** and left **50**, then **50** and left **0**; the transform
  bounded at 100 left staging at 100, 200 and 250 rows with 150, 50 and 0 pending; and the forced
  run bounded by the cursor walked windows of 100, 100 and 50, ending with 0 left.
- **What the round looked at.** No screen was **rendered**, and none needed to be: no SPA file
  changed. The commands were exercised — the parsers by the unit tests, the workers by the
  integration tests over the test database — but **no scrape against the origin site was run**, and
  the numeric evidence above is synthetic in that sense. That is the gap this entry declares.

## 2026-10-13 — the NER purge stops being the write with no way back (#94)

- **Range:** `84bb5f0..95796c3`
- **Pages:**
  - `guides/curate.md` — updated (the NER veto no longer claims to reach backwards: it bans and
    deletes nothing; the retroactive half is **Expurgar do passado**, with its preview, its
    `archive_ner_purge_log` and its undo, and the screen's table now says both halves are reversible;
    the paragraph that put the veto under "What has no way back" is gone)
  - `guides/curate.pt.md` — updated (the translation of the same section)
  - `guides/data-model.md` — updated (`archive_ner_purge_log` joins the ledger table, the conflict
    ledger row names the spellings it now restores, and `domain_ner_exclusions` says the row itself
    deletes nothing)
  - `guides/data-model.pt.md` — updated (the translation of those rows)
- **Why the round exists:** the report named `guides/curate.md` and `guides/data-model.md`, and the
  API delta was the four purge routes. The change moves a destructive write out of a reversible
  toggle, so every sentence that described the old coupling had to be re-read, not just the routes.
- **What the round measured.** Full suite **1591 passed** (`uv run pytest`, with
  `TEST_DATABASE_URL` pointed at the test database on 5434), `ruff check` and `ruff format --check`
  green, `basedpyright` **0 errors**, `alembic check` reporting no new upgrade operations after the
  new migration was applied, `bun run --cwd apps/curator typecheck lint build` green, and
  `mkdocs build --strict` green. The five new integration tests pin the plan/apply/ledger round trip,
  the spelling restore on both the NER purge and the conflict undo, the 409 on a second undo and the
  veto surviving the undo.
- **What the round looked at.** `/entidades/excecoes` was **rendered** on the dev stack (the API on
  `scrinalia_zeroed`, the built SPA served by the API, a scratch session created for the round and
  deleted after, the headless shell driven over CDP). Seen in the pixels: the veto card stating
  "Vetar não exclui nada", the **Expurgar do passado** card with its preview button, the
  **Ledger dos expurgos** card, the preview reporting the entities and their links, the purge writing
  a ledger row, and the undo marking that row "restaurada". The non-empty preview needed a matching
  entity, so one **temporary** orphan entity (`misto`, `ORG`) was inserted into the zeroed database
  and removed afterwards, together with the ledger row and the scratch session; the round trip was
  driven through the screen. That is the one synthetic input this entry declares.

## 2026-10-13 — the tag axis is the subject axis (#83, #84)

- **Range:** `95796c3..32d19f1`. The range ends at the second of the two commits that carry the
  change (the API/domain one is `5055312`, the curator one is `32d19f1`), so the floor closes the
  whole change. `guides/operate.md` declares `models/enums.py`, which moved, so it was read and not
  skipped.
- **Pages:**
  - `guides/curate.md` — **updated**: the *Classificar* tab has **two** destinations now — a drawer,
    or not-a-subject — instead of three. The `FACET` row leaves the state table, the row's evidence
    loses the facet, and the producer/place/person cases move to the **entity axis** (a type `LOC`,
    `PER`, `ORG` that search and the public projection read) and to the tag × entity conflict screen;
    the `PUT`/`DELETE /api/v1/taxonomy/tags/{tag_id}/facets/{facet_type}` routes are gone. The
    *Não é assunto* section stops promising that "only the subject classification stops guessing":
    confirming **also bans the spelling at `TAG` scope**, the ban deletes nothing, and the purge
    stays a deliberate act behind its preview and ledger. It documents the new read-only
    `POST /api/v1/taxonomy/tags/subject-exclusions/preview` (`AUTHENTICATED`) with its
    `applicable`/`blocked`, the refusal of a term whose tag is already in a drawer
    (`SUBJECT_EXCLUSIONS_BLOCKED` / `SUBJECT_EXCLUSIONS_PARTIAL`, `blocked`, `created`, `banned`), and
    the undo's `removed` **and** `unbanned` lifting only the ban this decision planted. The Stopwords
    tab and its purge preview now carry the ban's `source` (`HUMAN` / `CONFLICT` / `EXCLUSION`).
  - `guides/curate.pt.md` — **updated** (the translation of the same three places).
  - `guides/data-model.md` — **updated**: `archive_tag_facets` leaves the subject table (a tag is a
    drawer or not-a-subject; what a place, a producer or a person *is* belongs to the entity axis),
    `domain_stopwords` gains `source` and `domain_subject_exclusions` gains `ban_created`, the
    bidirectional-governance section separates `save_stopwords` (moves the scope) from
    `ensure_tag_ban` (widens and never narrows), and the ledger note says `ban_created` belongs to
    both writers of a ban.
  - `guides/data-model.pt.md` — **updated** (the translation of the same).
  - `README.md` — **updated**: the front door still said a provenance-or-geography tag carries an
    `archive_tag_facets` row; it now names the entity axis and the ban. (Not a sourced page — the
    freshness report cannot flag it, and it was found by reading the change.)
  - `guides/operate.md` — **no-change**: the `macro-category` worker's unit and its pending rule
    (`is_subject_candidate` + the exclusions) never read the tag catalogue's states, and the
    diagnostic SQL counts `macro_category_id IS NULL`, which the dropped table never entered. The
    page declares `models/enums.py`, which moved, so it was read and not skipped.
  - `adr/index.md` — the implementation change already links ADR 0013; the coverage gate's ADR check
    is green. `adr/0008-...md` was **updated** in the same commit: it still said `is_place_term`
    "claims it for the PLACE facet" and that a place kind "claims the PLACE facet", which ADR 0013
    makes false. The distinction ADR 0008 draws is kept and the destination moves to the entity axis,
    recorded there as an `Amended by ADR 0013` blockquote and named in ADR 0013's `Amends:`.
- **Why the round exists:** `freshness.py` printed **"Every page is fresh"** because the hook reads
  commits and the whole change is uncommitted — the report named nothing, so the triage was driven by
  the working-tree diff. That diff moves `curate.md`'s declared sources (`api/controllers/**`,
  `services/tag_service.py`, `repository/tag_repo.py`, `models/enums.py`,
  `packages/api-contract/openapi.json`, and the SPA `routes/**`) and `data-model.md`'s
  (`models/**`, `repository/tag_repo.py`). The API delta is two routes removed and one added.
- **What the round measured.** `uv run pytest testing/unit/docs -q` — **28 passed**;
  `testing/unit/docs/test_documentation_coverage.py` — **7 passed** (screens, tables, settings,
  workers, ADRs and the API-resource check); `uv run mkdocs build --strict` green. The full Python
  suite and the SPA build belong to the round that lands the change and were not re-run here.
- **What the round looked at.** The screens were **rendered**, not inferred. The built SPA was served
  by the API (`create_app()` mounts `apps/curator/dist`) against the reference collection, with a
  scratch session created for the round and deleted after, and the headless shell drove three routes
  over CDP. Seen in the pixels: *Classificar* (`/assuntos/tags?aba=classificar`) with the four chips
  — `Todas`, `Sem decisão`, `Não é assunto`, `Confiança baixa`, **no `FACET`** — the row's `Decidir`
  column reduced to the category select with no producer/place buttons, and the header reading
  "204 tag(s) neste estado", which is the same 204 the SQL count of undecided tags reports. *Não é
  assunto* (`/assuntos/excecoes`) with "4 candidatos · 4 são lugares (o eixo de entidades os carrega)",
  the `é lugar` badge and the new hint "quem carrega o lugar é o eixo de entidades (LOC)", the
  disclosure sentence naming the ban, and "139 termos fora do eixo de assunto" — the measured
  population. *Stopwords* (`/assuntos/tags?aba=stopwords`) with the origin badge on the terms the
  backfill classified `CONFLICT` (`veio de um conflito tag × entidade`) and **no badge** on the
  `HUMAN` ones (`1924`, `1926`), which is the 83/5 split the migration produced. The **blocked**
  branch was rendered too, by putting one candidate tag (`ruas`, id 131) into `Mobilidade e
  Transporte` and shooting again: the row gained the `está em Mobilidade e Transporte` badge and its
  button went disabled; the mutation was reverted immediately and the pending count returned to 204.
  **Not** verified in pixels: the write itself from the screen (the refusal and the ban are pinned by
  the integration suite, which drives the real routes and the real `ban_created`/`source` columns).

## 2026-10-13 — the thumbnail worker runs against a local endpoint (#33)

- **Range:** `480fd36..153afb2` — the merge that carried the previous round, then this change. The
  change was **uncommitted during the triage**, so `freshness.py` printed "Every page is fresh"; the
  triage was driven by the working-tree diff, as the previous entry's was.
- **Pages:**
  - `guides/install.md` — **updated**: the settings table gains `S3_AUTO_CREATE_BUCKET` (default
    `false`) and the `S3_BUCKET_NAME` row stops saying the bucket "must already exist" without
    qualification; the *Object storage is not shipped* section now says the worker confirms the
    bucket once, before the queue, creates it only with the flag on, and that SeaweedFS answers
    `AccessDenied` to an upload into a bucket that does not exist — which is why the confirmation
    exists. It also states that `GET /system/health` reports the distinction and never creates
    anything.
  - `guides/install.pt.md` — **updated** (the translation of both places).
  - `guides/operate.md` — **updated**: the runner's flag table gains `--limit N` (a cap on the units
    of one run, honored by the workers that declare `limit` and refused by the others) and now says
    that `--batch` is **logged** when the worker does not declare `db_batch_size`; the `thumbnail`
    bullet names the bucket confirmation and the cap.
  - `guides/operate.pt.md` — **updated** (the translation of the same).
- **Why the round exists:** the change moves `core/config.py` (the install page's declared source)
  and `core/storage.py`, `api/system_health.py`, `workers/runner.py` and `workers/worker_*.py` (the
  operate page's), so both guides were read and both needed a text.
- **What the round measured.** Full suite **1608 passed** (`TEST_DATABASE_URL` pointed at the test
  database on 5434), `ruff check`/`ruff format --check` green, `basedpyright` **0 errors**,
  `alembic check` reporting no new upgrade operations, `mkdocs build --strict` green. Against the
  local SeaweedFS and the reference collection the worker went from **0/97** to **97/97**
  descriptions with `storage_thumbnail_uri`, **97** objects under `thumbnails/`, **0**
  `thumbnail_failed`, and a `SUCCESS` row in `archive_worker_runs` (id 14, `trigger=CLI`, 55.5 s).
  The refusals were exercised: `--limit 2` processed exactly 2, `--limit 2` on `ner` was refused
  with the list of workers that declare it, and `--batch 2` on `thumbnail` logged that the value was
  ignored. `S3_AUTO_CREATE_BUCKET=true` created a scratch bucket on the endpoint (deleted after the
  measurement), and the flag-off path refused with the bucket and the `aws s3 mb` command named.
- **What the round looked at.** No screen was **rendered**, and none needed to be: no SPA file
  changed. The storage refusals are pinned by unit tests and were also exercised by hand against the
  real endpoint. **Not** verified in pixels: the *Diagnóstico* storage card, which the probe's two
  branches feed — those branches are pinned by `testing/unit/api/test_system_health.py`.
- **Divergence the round surfaced.** The CLI could not write its own ledger row:
  `archive_worker_runs` carries a foreign key into `auth_users`, and a process that imported only the
  archive models failed to flush the insert with `NoReferencedTableError`; the ledger swallows a
  bookkeeping failure by design, so a CLI run left no line while the panel's runs did. Fixed in the
  same change: `scrinalia.metadata.load_all_models` is the one definition of the model packages, and
  `migrations/env.py` and `WorkerRunLedger` both call it.

## 2026-10-13 — the pre-release pass for 1.2.0

- **Range:** `153afb2..HEAD`. The round was **uncommitted during the triage**, so `freshness.py`
  printed "Every page is fresh"; the triage was driven by the working-tree diff, as the two previous
  entries' were. Only three commits followed the ledger's floor (`153afb2`) — the entry that closed
  the thumbnail round and its test — so no page's `sources:` had moved when the reading began, and
  none of the drift below was a source delta either.
- **Pages:**
  - `README.md` — **updated**: the status line moves to `1.2.0`; the *no-undo* paragraph, which
    named three writes that had since become reversible; the runner snippet gains `--limit N`;
    `/sistema/workers` is read-only for configuration since #53; the unauthenticated list gains the
    first-run routes; the `worker_*.py` claim gains its exception.
  - `docs/index.md` and `docs/index.pt.md` — **updated**: "Scrinalia is at 1.1" → "at 1.2".
  - `guides/install.md` and `guides/install.pt.md` — **updated**: the two `Sistema › …` breadcrumbs,
    which name a group the shell does not have; "both doors close forever", which is true of the
    first-run route and not of the CLI; and the page's `sources:` gains the SPA navigation files it
    states facts about (`AppShell.tsx`, `lib/screens.ts`, `lib/settings.ts`), which the freshness
    report could never flag before.
  - `guides/operate.md` and `guides/operate.pt.md` — **updated**: the worked
    `conflict-judge --option host=…` example, which the runner **refuses** (measured:
    `InvalidWorkerSettingsError`); the `cleaning` unit cell; the claim that the CLI formats the
    duplicate-run refusal the way the API does; the `reset-password --password` comment.
  - `guides/curate.md` and `guides/curate.pt.md` — **updated**: the "Curadoria" nav group, which
    does not exist; "Four decisions" under five bullets; the ungoverned-worker count; the
    subject-exclusion preview no screen calls; the *Trechos* row, which called the removal
    reversible.
  - `guides/data-model.md` and `guides/data-model.pt.md` — **updated**: `archive_entity_merge_log`
    joins the ledger table; the author pair gains the two new ledgers; the ban-undo guard, which was
    scoped to two writers and belongs to one; four stamp keys and the value-keyed count;
    `NOT_PUBLIC_FIELDS`; `archive_tags` under the retire-with-`is_active` rule; "both merges".
  - `CHANGELOG.md` — **updated**: `## [1.2.0] - 2026-10-13` replaces `## [Unreleased]`, which
    carried **two** entries for ninety-one commits. The cycle's most consequential change — the tag
    axis becoming the subject axis (ADR 0013) and its route removals — was in neither.
  - `mkdocs.yml` — **updated**: ADR 0013 joins the site nav.
- **Why the round exists:** milestone 1.2 is complete, so this is the release preparation
  `CONTRIBUTING.md` asks for in one pull request — the version, the changelog, and the claims that
  drifted while no gate looked at them.
- **How the pages were read.** The freshness report names a page only when a declared source moved,
  and it cannot see a page with no `sources:` at all, nor a **number or a sentence** inside a page
  whose sources stayed put. This round therefore read every claim of the five pages against the
  code, one page per reviewer: the report was **silent** and every defect below was still there.
  Most predate the cycle; two were introduced by it — the entity rename landed without bumping
  "Four decisions", and the *Trechos* removal had never been reversible.
- **The gap no gate covered, now gated.** `docs/adr/0013-the-tag-axis-is-the-subject-axis.md`
  existed, was linked from `adr/index.md` and passed the ADR coverage check, and was **absent from
  the site nav**: `mkdocs build --strict` stays green because an unlisted page is an `INFO`, not a
  warning, so the ADR built and no menu reached it. The nav lists it now, and
  `testing/unit/docs/test_documentation_coverage.py` gained `test_every_adr_is_in_the_site_nav`,
  which reads `mkdocs.yml` as text — reachability is the nav, so the nav is what the gate reads.
- **A code defect the reading surfaced, and its gate.** `NOT_PUBLIC_FIELDS` listed
  `original_thumbnail_url`, which is **not** a field of `DocumentSummary` (it lives on
  `ArchiveDocumentDTO`), so the declaration withheld a field the internal summary never carried and
  the comment justified it as "the source link, superseded by `storage_thumbnail_uri`". The entry is
  gone, and `test_every_declared_non_public_field_exists` fails on the next name that is not a
  field: the partition test reads `internal − published − NOT_PUBLIC_FIELDS`, so a dead entry was
  invisible to it.
- **Two defects left standing on purpose, both now documented.** The conflict resolution's undo
  guards on `ban_created` but not on the ban's `source`, so it can lift a ban a person re-planted on
  the Stopwords screen — a real gap in `EntityRepository._lift_conflict_ban`, recorded in the
  data-model page rather than fixed here, because changing an undo's reach belongs to its own
  change. And `WorkerStamp("thumbnail")` is declared and never written, `worker_thumbnail`'s queue
  being led by `storage_thumbnail_uri`; the page says so now.
- **What the round measured.** Full suite **1610 passed** (`TEST_DATABASE_URL` pointed at the test
  database on **5434** — not 5433, which another project holds on this host; the compose file
  publishes `${TEST_DB_PORT:-5433}`, so 5433 would have talked to the wrong PostgreSQL),
  `ruff check` and `ruff format --check` green, `basedpyright` **0 errors**, `mkdocs build --strict`
  green, and the CI contract check replicated by hand: `uv run python -m scrinalia.api.dump_openapi`
  is **byte-identical** to the committed contract at `info.version` `1.2.0`. `uv.lock` and
  `bun.lock` carry the number and were regenerated, and
  `testing/unit/api/test_openapi_metadata.py` pins the served document, the installed distribution,
  `pyproject.toml` and the committed contract together.
- **What the round looked at.** No screen was **rendered**, and none needed to be: no SPA file
  changed. The UI statements corrected here are navigation labels and counts, read from
  `AppShell.tsx`, `lib/screens.ts` and `lib/settings.ts` — **not** observed in pixels, which is what
  a screen change would require.
- **Not verified, and said so.** The reviews did not re-measure the page's hardware figures (disk,
  RAM, wheel sizes), the Bun argument-forwarding note, or the contents of the `ACERVO_LANGUAGE`
  profile, and `install.pt.md` was checked by grep rather than read end to end for structural drift.
  The working tree also moved under the reviewers while the fixes landed, so each verdict above is
  against the tree at the moment it was read.
- **Not carried, on purpose:** the ADRs. `0010` still records "24 screens in `router.tsx`", `0012`
  still quotes the index's old "at 1.0", and `0011` still says "cycle 1.1": an ADR records the
  reasoning at the time, and none of those numbers is a rule the code has to satisfy.
  `src/scrinalia/api/openapi.py`'s docstring keeps "with `pyproject.toml` at 1.1.0" — that is the
  date of a **measurement**, and changing the number would falsify the record rather than update it.

## 2026-10-14 — the held majors adopted on purpose (#40)

- **Range:** `3c108cd..0ec13bb`
- **Pages:** three were reported stale and all three hold.
  - `guides/install.md` — **no-change**: the `DB_*` table, the "`DATABASE_URL` is a derived property"
    paragraph and the `docker-compose.test.yml` section still describe the code. The source this page
    declares that moved (`pyproject.toml`) is not quoted in its text, and the driver the DSN now
    names (`postgresql+psycopg2`) is not a setting an installer chooses.
  - `guides/data-model.md` — **no-change**: no table, column or index moved. `testing/conftest.py`
    gained a third thing it builds before `create_all` — the native enum types the models declare
    that the migration owns — and the page does not enumerate that list; it names the two SQL
    functions because a generated column depends on them.
  - `guides/operate.md` — **no-change**: no worker's unit, queue predicate, idempotency stamp or
    governance rule changed. The two rewrites inside them are internal spellings that return the same
    rows — `SELECT DISTINCT ON (archive_worker_runs.worker_name)`, and a `Row` that no longer needs
    `Result.tuples()` — and the panel and queue-count tests that read them are green.
- **Why the round exists:** `pyproject.toml` held two majors behind a comment (`pandas<3`,
  `sqlalchemy<2.1`), and adopting them changes the environment every installation and CI gets.
- **What the round measured.** The driver: `postgresql+psycopg2` is spelled out in `core/config.py`,
  `testing/conftest.py` and the CI environment, so the default cannot move under the project again.
  SQLAlchemy 2.1.4: `Enum(..., create_type=False)` stopped being ignored — the PostgreSQL impl of
  `domain_stopwords.word_scope` comes out `create_type=False` on 2.1.4 and came out `True` on
  2.0.54 — which cost the test schema `stopwords_scope`, `anomaly_type_enum` and
  `scrape_status_enum` and gave **851 errors at setup** (`type "stopwords_scope" does not exist`)
  until `conftest.py` created them from the models; nine `basedpyright` errors answered at their
  sites; `Result.tuples()` and the expression form of `distinct()` removed, the latter measured as
  `SELECT DISTINCT ON (archive_worker_runs.worker_name)`. pandas 3.0.6: the default string dtype is
  the new `str` and copy-on-write is on, neither of which this code meets (no frame is mutated in
  place, and the only frame read is BERTopic's topic info); `Series.__getitem__` now returns a union
  that includes a `Series`, and the two `int(row[...])` sites answer with a `cast`. Final: **1610
  passed** on a fresh test database with `-W error::DeprecationWarning`, `basedpyright` **0 errors**,
  `ruff check` and `ruff format --check` green, `alembic check` reporting no new upgrade operations,
  and the committed contract byte-identical to `dump_openapi` by hand.
- **What the round looked at.** No screen was **rendered**, and none needed to be: no file under
  `apps/curator/` changed.
- **Not verified, and said so.** The real engines were not run — the suite mocks the registry, so
  `bertopic` was imported, never used to cluster — and the lock was resolved on this host, not on a
  GPU installation, which the install page already says is a different lock.

## 2026-10-14 — the test schema also drops what it creates (#40)

- **Range:** `0ec13bb..3227e3d`
- **Pages:** `guides/data-model.md` — **no-change** (the previous entry judged the create half of the
  same helper): CI's migration step, which runs after the suite against the same database, failed
  with `type "anomaly_type_enum" already exists`, because `drop_all` skips a `create_type=False`
  type. `testing/conftest.py` now drops them after `drop_all`, from one generator shared with the
  create, and no table, column or index moved.
- **What the round measured.** The CI sequence replicated on a fresh test database: 1610 passed,
  `pg_type` and `pg_tables` empty after the teardown, `alembic upgrade head` applying every
  migration, and `alembic check` reporting no new upgrade operations.

## 2026-10-14 — the stamp names the producer (#41, #70)

- **Range:** `f240c71..52ed890`
- **Pages:** three were reported stale by `docs/_hooks/freshness.py` and all three changed.
  - `guides/operate.md` — **updated**: the queue table and the identity paragraph (five of the nine
    stamps now carry the producer), the `--limit` row (six workers, not `thumbnail` alone), the
    `--option` coercion (the declared type, not just `true`/`false`), the reprocessing section (a new
    producer re-queues by itself; `force` reaches `ner` and `typology` and clears the `ERROR`), the
    new *Trying a configuration before saving it* section with the measured `0` → `4.465`, and the
    route table's preview row. The paragraph that recorded the old trap — "`embedding_v1` is the MD5
    of the text, not the identity of the model, so changing `torch` does not put a single description
    back in the queue" — was the defect this round removes, and it now says what `?` does and does
    not answer.
  - `guides/data-model.md` — **updated**: the `execution_log` key table and the value-keyed paragraph
    (six keys, the identity, the two producers deliberately outside it).
  - `guides/curate.md` — **updated**: the `Conferir impacto` button of `/configuracoes/workers`, and
    why the number clears when a field moves.
- **What the round measured.** The forced-run defect, with a throwaway test (deleted) against the
  test database: `quality-validator` with `force=True` counts the same unit *after* it is stamped
  (`before=1 after=1`), and its loop had no cursor, so the documented command
  `runner quality-validator --option force=true` never ended. `ner` and `typology` advance only
  because the stamp leaves the queue (`before=1 after=0`), which is exactly the clause `force` drops.
  The identity itself: `describe_config` for `cpu_local` and `gpu_cloud` differs only in `device`, and
  the whole output is hashed on purpose. The suite: **1660 passed, 1 skipped** (the skip is the
  conflict-judge's counter-parity case, which has no queue); `basedpyright` **0 errors**;
  `ruff check` and `ruff format --check` green; `alembic check` reporting no new upgrade operations;
  the committed contract regenerated from `dump_openapi`.
- **What the round looked at.** The settings screen **was rendered**: headless shell + CDP against the
  dev server and a scratch database (`scrinalia_render`, 4.842 documents) with a session row inserted
  and deleted for the round. With the collection stamped by the producer in the code, the default
  configuration answered `0 na fila com esta configuração (nada foi salvo).`; typing
  `{"confidence_threshold": 0.9}` into the options field and pressing **Conferir impacto** answered
  `4.465 na fila com esta configuração (nada foi salvo).` The screenshots are under `.render/`
  (gitignored), not in the repository.
- **Not verified, and said so.** The real engines were not run — the suite mocks the registry, and no
  vector, entity or typology was produced by a model in this round. The queue numbers of the *real*
  collection were not measured; the `4.465` above is the scratch database the render used. The
  installed versions are read for `torch`, `transformers`, `sentence-transformers` and `spacy` only:
  the spaCy model package (`pt_core_news_lg`) and the digest of the Ollama model stay outside the
  identity, because the first lives in the language profile and the second would take a network call
  on the panel's path — both documented on the page and left as a follow-up, not as a silent gap.
- **Consequence to expect.** Every unit stamped before this change — including a `DONE` — is pending
  again under the producer now configured, so the first run after upgrading re-reads the collection
  once. That is the fix working, and the preview is how to size it before paying it.

## 2026-10-17 — the bench family, and the rule axis with no rule to score (#114, #115, #116)

- **Range:** `52ed890..4436154`
- **Pages:** three were reported stale by `docs/_hooks/freshness.py`. All three are **no-change**, and
  the single commit that moved a declared source is `ef11773` — the refactor the validator bench
  needed, which named three functions and a separator instead of changing behaviour.
  - `guides/curate.md` — **no-change**: nothing on a screen or a route moved. The rules screen still
    offers the same three `rule_kind`s with the same three writes, and the paragraph that says a
    `VALIDATE`/`LLM_CHECK` rule only flags and never rewrites still holds. The change to
    `models/enums.py` is a named constant plus two accessors for a format that already existed.
  - `guides/data-model.md` — **no-change**: no table, no column and no constraint changed.
    `anomaly_reasons` keeps its type and its `CODE:payload` content — the separator became
    `ANOMALY_REASON_SEPARATOR` in `models/enums.py` and the facet's SQL reads it instead of a literal
    `":"`, which is one definition where there were two. The `archive_cleaning_rules` row and the
    `rule_kind` paragraph are untouched.
  - `guides/operate.md` — **no-change**: the worker table, the queue predicates and the identity
    paragraph describe behaviour that did not move. `worker_quality_validator.py` gained
    `matched_rule_labels`, `llm_check_reason` and `rule_flag_label`, and `_compile_rules` became
    `compile_rules`; the worker marks the same documents with the same reasons and stamps the same
    producer.
- **What the round found.** The validator bench needed "did this rule fire", which existed only inside
  `evaluate_document`, so the answer became a function the worker and the bench share — and the pin
  between them is an integration test that runs the real worker and asks the bench what fired, with a
  rule carrying an `anomaly_reason` rather than its name.
- **What the round measured.** Against `memoriacuritibana` on 2026-10-16: the conflict judge agrees
  with the 49 human resolutions at **0.918** while a constant ENTITY answer scores 1.000 (Δ −0.082),
  and all four misses are the same direction at confidence 0.900 — high enough that the worker would
  have auto-resolved every one of them. The validator flags **4,583 of 4,831 documents (94.9%)**, of
  which `RULE_MATCH`/`LLM_SUSPECT` are **zero**: the catalogue holds one rule, inactive and `REWRITE`,
  so the per-rule axis has nothing to score and both benches refuse with that sentence instead of an
  empty table.
- **Not verified, and said so.** `xlm_roberta_local` was never executed — the weights are not in this
  machine's read-only Hugging Face cache — so its preset is wired at the code level only. The
  `granite_local` conflict judge answered 500 to every prompt (`granite4.1:3b`, whose llama runner
  crashes on this Ollama build) and the bench counted 49 engine failures rather than scoring them; the
  engine defect that makes that possible is #122. No screen was rendered in this round: the work is a
  bench, two refactors and a ledger.

## 2026-10-17 — the typology queue is gated on the stamp (#117)

- **Range:** `4436154..22bfe62`
- **Pages:** one was reported stale by `docs/_hooks/freshness.py` and it **changed**.
  - `guides/operate.md` — **updated**: the queue table's `typology` row no longer says "documents with
    no typology" (the clause is gone) and now names the label set as part of the stamp; the "catalogue
    changed" bullet gained the typology catalogue and the refusal that clears an answer; the `force`
    bullet no longer claims `typology` never reclassifies a document that already has one, which was
    the sentence the change falsified; and the paragraph that sizes a re-queue now says that **every**
    stamped description is pending once after this upgrade, not only the ones stamped by an older
    producer. The Portuguese page carries the same four edits.
- **What the round measured.** Against `memoriacuritibana` on 2026-10-17, and the numbers are the
  argument: `count_pending` answered **4,205** under floor 0.40, floor 0.90, two column sets and two
  presets — 4,813 ai-writable documents minus the 608 carrying a typology, exactly — so no change the
  identity signs could reach a single classified document. After the change the same four
  configurations answer **4,813**. The 608 split into 135 with a typology stamp and **473 with none**;
  the 4,223 without a typology split into 4,188 never seen and 35 seen and refused.
- **What the round checked.** The pair is pinned by integration tests that read the real queue through
  the worker's own `pending_conditions`: adding, renaming and retiring a typology each re-queue the
  affected documents, an unchanged catalogue re-queues nothing, a description the current producer
  settled stays out while the 0.55 floor reaches the one the 0.40 floor settled, and a refusal clears
  the answer another producer wrote. Four unit tests pin the identity itself: order-independent,
  different for an added, renamed, retired or replaced drawer, and still separating the floor and the
  columns.
- **Not verified, and said so.** The re-classification of the 4,813 was **not executed** — the queue
  was counted, not paid: at the measured ~2 s per document on the title alone that is about 2.7 hours
  of CPU, and no model was run against the real collection in this round. So "the 473 legacy answers
  are re-read" is a projection from the predicate, not an observation, and the first run after
  deploying is where it becomes one. The clearing on refusal is pinned against a fixture engine in the
  test database, not against the real classifier: `gemma`/`mDeBERTa` weights are not exercised here.

## 2026-10-17 — the typology bench compares label formats (#112)

- **Range:** `22bfe62..a554cbe`
- **Pages:** none. `docs/_hooks/freshness.py` reported every page fresh: the round touched
  `testing/evaluation/typology_quality.py`, its tests and the evaluation README, and no guide declares
  a bench as a source. The entry exists to record the verdict and to advance the floor, not because a
  page was at risk.
- **What the round measured.** The three formats on 111 of the 112 labelled rows, CPU, at the
  shipping configuration `deberta_typology:cpu_local:original_title:0.40`: `bare` agrees **0.775**
  with macro-F1 0.484 and 5.4% abstention; `trata_de` **0.784** with 0.478 and 7.2%; `sentence`
  **0.604** with 0.414 and **29.7%**. The plans are where `sentence` breaks — recall 0.956 → 0.511,
  with 20 of them abstaining — which is #30's lost entailment reappearing exactly where
  `classifier_labels` warns it does.
- **What the round decided.** "Ofício / Memorando" takes exactly **8** of the 11 descriptions no
  typology covers **under all three formats**: the dustbin is not a wording problem, and no label shape
  makes an uncovered form covered. `bare` wins, so the default is not changed, nothing moves in the
  worker, and #30 keeps its decision with the measurement it never had. Adopting a proposition would
  have cost a full re-queue under the identity #117 had just made meaningful, for no measurable gain.
- **Not verified, and said so.** The second half of the issue's observation — that with the archival
  history added the same drawer answers nothing because the model abstains on all 11 — was **not**
  re-measured: the round was scoped to the shipping configuration, where the default stays. It is a
  question about the columns that #109 already priced at 2.62× the cost, not about the label shape.

## 2026-10-17 — the typology records the refusal it saw (#110)

- **Range:** `a554cbe..7a40f14`
- **Pages:** three were reported stale by `docs/_hooks/freshness.py`; two changed and one is
  no-change, and the reason it is no-change is the honest part.
  - `guides/data-model.md` — **updated**: the `archive_ai_review_queue` paragraph said the queue
    carries `SUBJECT_LOW_CONFIDENCE` "for tags the subject classifier could not place"; it now also
    names `TYPOLOGY_LOW_CONFIDENCE` and says that row is where the score the run saw is kept, because
    `typology_id` stays NULL for a refusal and for a description no run reached.
  - `guides/operate.md` — **updated**: the `typology` worker's bullet said only that it classifies by
    zero-shot; it now says what a refusal leaves behind.
  - `guides/curate.md` — **no-change**: it moved only because `models/enums.py` is one of its declared
    sources, and no screen reads this row. The issue's Definition of Done deliberately left the
    curator card out — the read side has to answer the count, and surfacing it is a separate decision,
    which is now **#129**: the descriptions the classifier refused need a screen, and that issue decides
    first whether it belongs to `/arranjo/tipologias` or widens `/qualidade/anomalias`.
- **What the round measured and verified.** The migration was applied against a scratch database and
  against the development one: `upgrade head` from `3f9c1a7be204` adds the value, the enum then lists
  all three, and `downgrade -1` runs. The development database's revision matched this migration's
  `down_revision` exactly, so nothing else moved with it. `alembic check` reports no new upgrade
  operations.
- **Not verified, and said so.** No worker was run against the real collection, so the number of rows
  this writes there is a projection from the #109 abstention rate (0.000 on the title at 0.40, 0.020
  with the archival history) and not an observation. The curator screen that would make these rows
  actionable does not exist and is not in this DoD.

## 2026-10-17 — the typology bench simulates a catalogue edit (#111)

- **Range:** `7a40f14..5da851b`
- **Pages:** none. `docs/_hooks/freshness.py` reported every page fresh: the round touched
  `testing/evaluation/typology_quality.py` and its unit tests, and no guide declares a bench as a
  source. The ledger entry exists to record the verdict and advance the floor.
- **What the round measured.** Four catalogues over the same 111 signed rows at the shipping
  configuration: as it is (agreement 0.775, macro-F1 0.484, 25 misses), without "Ofício / Memorando"
  (**0.856**, 0.558, 16), with the three missing forms named "Livro de Registro" (0.378, 0.272, 69) and
  with them named "Livro de Sepultamento" (0.703, 0.476, 33 — against a predicted 33).
- **What the round concluded.** On this axis the **name is the taxonomy**: "Ofício / Memorando" is a
  form the collection has zero of and the model's third favourite answer; "Livro de Registro" collides
  lexically with the fonds' own titles ("Registros Fotográficos") and collapses the axis; a
  discriminative name takes exactly its documents. A definition documents and cannot decide, because
  #30 keeps it out of the prompt — so the catalogue edit is a naming decision, and the bench prices one
  in about four minutes against a 2.9-hour re-queue.
- **Not verified, and said so.** No catalogue change was written to the database: the round measured
  simulations, and the real re-queue cost is the projection from the 2.2 s per document #109 measured.
  The 11 control rows read as misses in the extended catalogues because the gabarito says `null` for
  them — correct for the product, wrong for the placar, which is the re-labelling issue #111 names.

## 2026-10-17 — the typology catalogue decided, and the strata follow it (#111)

- **Range:** `5da851b..HEAD`
- **Pages:** none reported stale. The round touched `testing/evaluation/typology_quality.py` and its
  tests; no guide declares a bench as a source, and the catalogue itself is data of the installation
  and does not ship, so nothing a page documents moved.
- **The decision, taken and applied.** Three forms with zero instances retired (`Ofício / Memorando`,
  `Ata de Reunião`, `Dossiê Funcional`), three forms the collection has added with names chosen for their
  discriminative power (`Livro de Sepultamento`, `Requerimento à Câmara Municipal`, `Publicação
  Impressa`), and three definitions corrected to say what the curator's own labels say the drawers hold.
  Measured: agreement 0.775 → **0.865** without the dead forms, and the three added forms take exactly
  their documents (8 burial registers at 0.968–0.982, 2 Câmara petitions at 0.926–0.939).
- **Reversibility.** The typology catalogue has no revision ledger, so the before-state of all six
  touched rows — names, ids and the full previous `context_description` — is recorded in the issue
  comment that states the decision. That is what makes the change undoable.
- **Verified.** `--pick` runs against the new catalogue and proposes 8/8, 3/3 and 1/1 for the three new
  strata; `count_pending` is 4,813 before and after, because the re-queue #117 declared was already owed
  and this edit changes what that run produces, not whether one is owed.
- **Declared, not closed.** The control bucket proposes 1 of 1 candidate, so keeping a false-positive
  control now needs the curator to name what stays out of scope; 31 descriptions match no stratum and are
  photographs `PHOTO_STRATUM` misses; and the revised gabarito needs a human signature, which the bench's
  `status` gate exists to require and which is not mine to give.

## 2026-10-17 — a bench for the NER extractor (#113)

- **Range:** `5da851b..a76dc63`
- **Pages:** none reported stale. The round touched `testing/evaluation/` and its tests; no guide declares
  a bench as a source, and the set's shape is versioned in `testing/evaluation/README.md`, which is not a
  page of the site.
- **What the round built.** `testing/evaluation/ner_quality.py`, term-level P/R/F1 per type and overall
  with exact match only, a relaxed recall printed beside it, and the misses partitioned into hits,
  boundary, type confusion and missing plus spurious. Nothing is written: the session is opened, read and
  rolled back. 48 unit tests and 16 integration tests, one of which pins the composed text against what
  the worker hands the engine.
- **Three places the Definition of Done could not be met as written**, all recorded in the issue:
  **there are no spans anywhere** (`EntityExtractionEngine.extract` returns a DTO with `name` and
  `entity_type`, and the link table has no offsets), so the boundary breakdown is a token-containment
  measure that counts the defect without locating it; `input_text` is deliberately not in the file, since
  the sheet reads the text through the worker's own composition; and a row is *read* when it carries a
  `confidence` or a `note`, so an untouched proposal is counted apart rather than scored as "no entity".
- **What it found in the collection, measured directly.** 1,650 documents carry `worker_ner_v2 = "DONE"`,
  41 carry `worker_ner_v1 = "DONE"`, 3,142 carry no NER stamp at all, and **not one carries a producer
  fingerprint**: the NER output is unattributable in full, which is the concrete case behind #135.
- **Not verified, and said so.** No human-corrected set exists, so there is **no measurement of the
  extractor yet** — only the plumbing proof (a set whose `expected` is the live extraction scores 1.000,
  and a stored set with one truncated term shows the exact-versus-relaxed pair). The proposal waits for a
  curator, and the first real number is the one measured against the signed set.

## 2026-10-18 — the hybrid ranking, and the numbers the issue was missing (#38)

- **Range:** `a76dc63..8b92fef`
- **Pages:** `guides/curate.md` — **updated**: the search section named two rankings and carried a
  measurement that was not about them, and now names the three with the rule that decides between them
  and the limit of the evidence. `guides/install.md` — **no-change**: `lib/screens.ts` moved, and what
  moved is the one-line description of an existing screen; no installation fact, screen count or label
  changed.
- **The issue's premise was measurably wrong, and that was the first finding.** `#38` quoted
  *"MRR fell 0.019 while Hit@10 rose to 0.625"* as evidence that the semantic ranking was weak against
  the lexical one. Both numbers come from `9a075bc` (2026-10-04) and are the before/after of the
  **excerpt catalogue on the semantic arm** (`MRR 0.358 → 0.339`, `Hit@10 0.562 → 0.625`), measured on
  3,608 descriptions. No lexical-versus-semantic comparison existed anywhere in the repository, the
  bench the issue named (`retrieval_quality.py`) has no lexical arm and never had one, and the page
  that repeated the number — `guides/curate.md` — cited the *improved* figure as proof of weakness.
- **What the round built.** `mode=hybrid`: the full-text and semantic rankings built independently and
  fused by `reciprocal_rank_fusion` (`domains/archive/domain/search.py`, `RRF_K = 60`), over the
  top `RRF_DEPTH = 100` of each arm. `total` is the union of the full-text matches with the semantic
  **window** and not every embedded document; the page is the fused window first and the full-text
  order after it; `rank` is the fusion's score inside the window and the relevance of the ordering
  outside it. The facet rule survives the fusion: the window is rebuilt for each dimension that
  excludes its own filter. One `SearchMode` alias replaces the `Literal` written three times, and the
  full-text mode stays the default, so a lexical request still never loads the model.
- **The measurement, per stratum, through the product path** (`retrieval_modes.py`, 16 labelled
  queries, 4,831 descriptions): sentence — lexical `0.438 / 0.258`, semantic `0.562 / 0.293`, **hybrid
  `0.625 / 0.296`** (Hit@10 / MRR); term — lexical `0.875 / 0.703`, semantic `0.562 / 0.338`, **hybrid
  `0.938 / 0.679`**. The fusion wins on both strata and is therefore the mode that removes the choice;
  it is not a free win, and the term stratum says so: one more query inside the top ten and still
  0.024 below the full-text ranking on MRR, because agreement demotes a confident full-text hit the
  semantic arm disagrees with.
- **Two properties the arithmetic had to be corrected for, both measured.** RRF is **not** a dominance
  order — a first place plus a third beats a second place twice by 8·10⁻⁶ (`1/61 + 1/63` against
  `2/62`), because the reciprocal is convex — so neither the helper's docstring nor the tests claim
  that a shared document always wins. And the window depth is a parameter that moves the result: the
  pre-implementation simulation over the top 50 of each arm gave the term stratum `MRR 0.722`, the
  shipped window of 100 gives `0.679`.
- **Latency is the full-text one plus about 7%** (6.40 s against 5.46 s per query on the sentence
  stratum, 13.69 s against 12.85 s on the term stratum, measured with the model loaded outside the
  timed loop). The absolute numbers are high and are **pre-existing**: they are the cost of a broad
  term in the full-text arm, which the fusion adds six semantic window queries to rather than creates.
- **What the round looked at.** Two screens **were rendered**, not inferred: the headless shell over
  CDP against the dev server and the scratch database (`scrinalia_render`, 4,842 descriptions), with a
  session row inserted for the round and deleted after. `.render/hybrid.png` shows the hybrid mode
  selected, the note on screen and the results of `matadouro` — 139 descriptions, the facets filled,
  and a description **without the term in its title** ranked above the ones that carry it, which is the
  fusion visible on the page; `.render/semantic.png` shows the semantic note and the same query
  answering **4,842 descriptions**, the whole embedded collection, which is the count the fusion
  exists to stop reporting.
- **Not verified, and said so.** The public surface's `mode=hybrid` is covered by the contract and by
  the repository tests, and was **not** rendered: no screen was opened against `/api/v1/public`. The
  latency was measured against the live collection on this machine and not under load, and the bench's
  labelled set remains sixteen queries whose gold is derived from the title — the report prints that
  limit next to every number, and the numbers themselves are in the issue comment, not in a page.

## 2026-10-18 — the search that filtered after joining, and the page that under-declared its sources (#140)

- **Range:** `8b92fef..c884152`
- **Pages:** `guides/operate.md` — **updated**: its last known-limit bullet said that ranking by
  semantics alone was weaker than the lexical one and that *combining the two rankings is open work*.
  Both halves had stopped being true in #139, which shipped the fused mode, and the page had never
  declared the search code among its `sources:`, so no freshness report could see it. The bullet now
  says what decides between the three modes, points at the curation guide that owns the table and at
  the bench that measures them, and the four files it depends on (`domain/search.py`,
  `repository/document_repo.py`, `services/document_service.py`, and the two retrieval benches) are
  declared — which is why this round was reported at all.
- **The defect the round fixed, measured before it was touched.** A selective term (`enchente`, 12
  matches) took **18.0 s** and a broad one (`curitiba`, 3,286) **6.6 s**; two facet queries were 98% of
  that. The term reached the facets as an `OR` of correlated `EXISTS`, so it was evaluated once per
  link row — 64,504 entity links to find 12 descriptions — and the `OR` kept the planner away from the
  `search_vector` GIN index. The hardware was ruled out by measurement: 78 MB table, 128 MB
  `shared_buffers`, 99.98% cache hit ratio, `shared hit=598,994` and zero reads in the plan, no
  container limits, `VACUUM (ANALYZE)` worth 72 ms of 9,020. The commit before the fusion took
  **17,974 ms**, so nothing here was the fusion's doing.
- **What the fix changed.** The full-text arm is a set of description ids (text ∪ tag ∪ entity),
  computed once per query and handed to the page, the count and every facet; the taxonomy boost reads
  the same two sets instead of a correlated `EXISTS` per candidate row; the count stopped computing a
  rank expression it does not read; and the fused mode's candidate clause became one union of two id
  sets instead of an `OR` of them (2.1 s → 0.31 s on its own).
- **The measurement, and the one regression.** Eighteen query/mode/filter cases on the live collection,
  results **identical** — same ids, order, ranks to ten decimals, `total` and all five facet counts:
  lexical 17.5 s → 0.21 s and 6.4 s → 0.41 s, hybrid 18.0 s → 0.31 s, semantic unchanged at 0.15 s. One
  case got slower, a term combined with a highly selective facet filter (0.19 s → 0.29 s), because the
  term set is resolved before the filter now — the term is the floor for any query that has one.
- **What was looked at, and what was not.** The screens were **not** rendered and did not need to be:
  no SPA file changed, and the 18-case digest is the evidence that the answer is byte-for-byte the one
  the routes already served. The public surface was not exercised separately.
- **A guard, and proof that it bites.** `testing/integration/archive/repository/test_search_predicate_shape.py`
  pins the shape of the emitted SQL, because the defect is invisible to a behavioural test: reverting
  the clause returns exactly the same page. Both guards were run against the code before the fix and
  fail there, and pass after it.

## 2026-10-18 — the judge that wrote a failure as a verdict, and the preset that could not run (#122)

- **Range:** `c884152..5bfb1f8`
- **Pages:**
  - `guides/install.md` — **updated**: the resource table said the presets name `granite4.1:3b` and
    `gemma4:e4b`, and the first was retired in this change, so the table names one model now. The
    "Ollama is down" section gained what the retirement means for an operator: the name is not
    offered, the health probe no longer requires the model, writing it is refused, and a row written
    before the retirement resolves with the reason on the screen.
  - `guides/install.pt.md` — **updated**: the same two places, same structure.
  - `guides/operate.md` — **updated**: the `conflict-judge` bullet now says a call the engine could
    not make raises instead of becoming a verdict, so the pair leaves no row and is asked again on
    the next run; the `--preset` example no longer lists the retired name.
  - `guides/operate.pt.md` — **updated**: the same two places.
- **The measurement the retirement rests on, taken in this round.** Ollama 0.24.0 on this machine:
  `granite4.1:3b` answers `{"error":"llama runner process has terminated: signal arrived during cgo
  execution"}` to a one-word prompt, while `gemma4:e4b` and `gemma3:4b` answer `ok` on the same
  server. The model **is installed**, so the health probe's missing-model list could never have
  caught it — which is why the retirement is a code decision and not an installation note.
- **What the fix changed, and the gate that proves it.** The engine raises `EngineExecutionError`
  instead of returning `winner="TAG"` with confidence `0.0`; the worker leaves no `llm_decision` and
  the pair stays pending; the bench's `FAILURE_REASON_PREFIX` matching is deleted. The pair of tests
  is `testing/unit/archive/engines/test_ollama_tag_entity_conflict.py` — a transport error, a 500 and
  a 200 whose body is not the schema all raise, and a valid body still returns a verdict — and the
  worker integration test: no queue row, `count_judged == 0`, and the pair is asked again on the next
  run.
- **What was rendered.** The panel's worker screen, with a session row inserted for the round and
  deleted after it: `.render/workers-122.png` shows row 5 (`conflict-judge`) resolving to
  `ollama_judge · gemma_4b_local — gemma4:e4b`, and `.render/workers-122-stale-open.png` shows the
  same row after a `granite_local` row was written directly into `archive_worker_settings` (deleted
  after the shot): the row reads `padrão alterado`, resolves to `gemma_4b_local`, and the note at the
  bottom carries the reason. The retired name appears in no preset select.
- **Not verified, and said so.** The bench was **not** run against the real model in this round: the
  measurement above is a direct call to Ollama, so the report's own columns (agreement, constant
  baseline, Δ) are unchanged from #114 and were not re-measured. The refusal of the retired name is
  covered by tests on `get_engine`, `describe_config` and the API's write path; it was not exercised
  through the SPA's save button. The title-quality axis's failure path was left as it was:
  `check_title` still swallows a transport error into `is_suspect=False` with confidence `0.0`, the
  same defect class in another worker, and it is outside this issue's definition of done — no test
  covers it either way, which is a gap this round did not close.

## 2026-10-18 — the engine of an LLM_CHECK rule stops being free text (#124)

- **Range:** `5bfb1f8..d18c3f0`
- **Pages:**
  - `guides/curate.md` — **updated**: the *Regras* section gained what the `LLM_CHECK` rule's two new
    selects are fed by (`GET /api/v1/quality/cleaning-rules/engines`, the title-quality axis's
    catalogue), that the pair is checked when the rule is written and refused as a `422`, that an
    empty engine still means the default, and what a rule written before that door does now.
  - `guides/curate.pt.md` — **updated**: the same paragraph, same structure.
  - `guides/operate.md` — **updated**: the `quality-validator` row of the queue table now says its
    producer identity is the "no model" one **also** when the rule's engine cannot be built, because
    that is the run the validator actually makes.
  - `guides/operate.pt.md` — **updated**: the same row.
- **The defect, measured before it was touched.** The screen's only hint was the placeholder
  `ex.: ollama`, and `ollama` is not a registered engine — the axis holds `ollama_title_check` alone.
  Nothing validated the pair on the way in (`CleaningService.create_cleaning_rule` checked the regex
  and nothing else), and the registry's `ValueError` escaped `worker_quality_validator.execute`, so
  the run was recorded `FAILED` and the validator validated nothing while the rule stayed active.
- **What the change is, in three pieces.** The catalogue is one definition
  (`describe_axis_engines`, shared with the operations panel) behind a new read route; the write
  validates the pair through the registry's own `describe_config` and raises
  `InvalidLLMCheckEngineError` (`422`) whatever the rule kind is; and the two readers of a rule saved
  before that door — `execute` and `producer_identity` — ask one question
  (`unbuildable_rule_reason`) and degrade to the deterministic stage and the "no model" identity.
- **What was rendered.** `.render/cleaning-rules-124.png`: the *Nova regra* form with `Tipo` =
  *consulta o modelo*, `Engine` = *padrão (ollama_title_check)* and `Preset` = *sem preset (o padrão do
  motor)*; the preset list read out of the DOM was
  `gemma_4b_local — gemma4:e4b`, and the placeholder that named a non-existent engine is gone. The
  catalogue the screen reads was checked against the live route before the shot:
  `[{"name":"ollama_title_check","presets":[{"name":"gemma_4b_local","config":{"model":"gemma4:e4b",...}}]}]`.
- **Not verified, and said so.** The refusal was exercised through the real route and the real
  service by the integration test (a `POST` naming `ollama` answers `422` with
  `InvalidLLMCheckEngineError`), but **not** by clicking *Salvar e ativar* in the browser. The legacy
  degradation is covered against the test database; no live run against Ollama was made, so the
  sentence the log carries in that path was read in the captured log, not on a screen.

## 2026-10-18 — the legacy stamps stop reading as a producer (#137)

- **Range:** `d18c3f0..e625d49`
- **Pages:**
  - `guides/operate.md` — **updated**: *What each queue means* now opens the stamp into the three
    things a slot can name (with a producer, without a known one, without a record) instead of one
    `processed` number; the paragraph on the `ERROR` mark says the legacy value is
    `PRODUCER_UNKNOWN` now and that the queue is untouched either way; the `/sistema/workers` row of
    the panel table says what the card shows.
  - `guides/operate.pt.md` — **updated**: the same three places.
  - `guides/data-model.md` — **updated**: the stamp vocabulary is two types with different writers
    (a status raises in an identity slot), the five identity keys and `PRODUCER_UNKNOWN`, and the
    migration that renamed the legacy rows — including what it deliberately did not touch (a key
    that was never there, and the embedding's bare text hash).
  - `guides/data-model.pt.md` — **updated**: the same paragraph.
- **What was rendered.** `.render/workers-137.png`: the headless shell over CDP against the dev
  server and the reference collection, with a session row inserted for the round and deleted after
  it. The NER card, expanded, reads `0 com produtor · 1.650 sem produtor conhecido · 3.181 sem
  registro` under `Fila (descrições)`, against `4.813` pending — the three numbers the issue asked
  to be readable, on the collection where the single number used to say 1.691.
- **The migration was run, not only written.** On the reference collection,
  `f647dd7e6ad2 -> a7c1e5b9d3f2` rewrote 3,511 document slots and 921 tag slots (`worker_ner_v2`
  1,650, `worker_quality_validator_v1` 1,650, `worker_macro_category_v1` 921,
  `worker_typology_classifier_v2` 129, and the retired `worker_ner_v1` and
  `worker_typology_classifier_v1` 41 each), with 0 fingerprints before and after and the pending
  counts unchanged. The downgrade was run too: the round trip returned 1,691 values to `DONE` and
  back to `PRODUCER_UNKNOWN`. `alembic check` reports no drift.
- **Not verified, and said so.** No worker was run after the migration, so no document was seen
  being healed from `PRODUCER_UNKNOWN` to a real fingerprint: that the next plain run re-reads those
  units is the predicate in `identity_stamp_conditions`, read in the code and pinned by the unit
  tests, not observed as a run. And the panel was read on the reference collection only — the tag
  breakdown of `macro-category` is covered by the repository test and was not looked at on a screen.

## 2026-10-22 — the thumbnail failure mark is the plain ERROR (#149)

- **Range:** `0c09f99..d1494f1`
- **Pages:**
  - `guides/operate.md` — **updated**: the failure count now names `ERROR` as the value and the
    `thumbnail_failed` key as the thumbnail's own ledger, instead of suggesting a second failure
    spelling.
  - `guides/operate.pt.md` — **updated**: the same paragraph, same structure.
  - `guides/data-model.md` — **updated**: the `thumbnail_failed` row names `ERROR` as the value, so
    the table no longer leaves the reader to infer it.
  - `guides/data-model.pt.md` — **updated**: the same row.
- **Measured, not assumed.** On the reference collection (`memoriacuritibana`) the key has **0**
  rows; the migration was run **up and down** on a scratch database with a seeded `True` row and
  returned it to `True` on the downgrade. The thumbnail queue and its `failed` count read the key's
  presence, not the value, so the queue is unchanged.
- **Not verified, and said so.** No screen changed, so no render was made; the panel's `failed`
  number for the thumbnail is covered by its counter test, not looked at in a browser. The #148 gate
  is test-only and has no documentation page.

## 2026-10-23 — the spaCy pipeline leaves the lock for a build step

- **Range:** `d1494f1..8af438e`
- **Pages:**
  - `guides/install.md` — **updated**: step 3 gains the install command
    (`uv pip install --python .venv/bin/python --require-hashes -r models/requirements.txt`) and the
    paragraph saying why the pipeline is not in the lock and that `uv sync` prunes it;
    `models/requirements.txt` joins the page's `sources:`.
  - `guides/install.pt.md` — **updated**: the same step and paragraph.
  - `guides/curate.md` — **no-change**: the report named it for
    `packages/api-contract/openapi.json`, and that file's whole diff in the range is `info.version`
    from `1.2.0` to `1.3.0` (`5a41a2d`). No route, schema or screen moved, so the page still holds.
- **Measured, not assumed.** `uv lock` resolved 214 packages without `pt-core-news-lg`;
  `uv sync --locked` uninstalled the package; the install command put it back in 6.06 s against a warm
  cache, and `importlib.metadata.version("pt-core-news-lg")` answered `3.8.0`. The requirements line
  carries the sha256 the lock used to hold.
- **Not verified, and said so.** The image was not built here: the Dockerfile step is that same
  command, run after `uv sync` in the same stage. And no Dependabot run has happened since the change,
  so the update job it exists for is still unobserved.

## 2026-10-24 — the entity link that could not say who wrote it (#135)

- **Range:** `d1494f1..1ac157d`
- **Pages:**
  - `guides/data-model.md` — **updated**: the `archive_document_entities` row carries `origin` and
    `created_at`, and says `created_at` is null for a link that predates the column.
  - `guides/data-model.pt.md` — **updated**: the same row.
  - `guides/curate.md` — **updated**: the `Assuntos` tab names the origin of each link, the
    `Confirmar` action and its consequence, and the fact that a confirmation which changes no names
    writes no revision.
  - `guides/curate.pt.md` — **updated**: the same paragraph.
- **Measured, not assumed.** On a copy of the reference collection (`memoriacuritibana`, 64.504 links
  over 4.811 documents) the migration ran up and down and `alembic check` reported no drift; the
  backfill left exactly **64.504** rows as `UNKNOWN` and none as `AI`. The screen was rendered against
  that copy migrated to head: `confirmada`, `IA` and `não rastreada` appear on the same list, and
  clicking `Confirmar` on an `UNKNOWN` row flipped it to `HUMAN` both in the database and on screen.
- **Not verified, and said so.** No NER worker was run after the change: the `IA` row in the render
  was written through `EntityRepository.bulk_link_entities` — the worker's own write path — and not
  by a full extraction. And a confirmation that changes no names writes no revision, so the
  `changed_by` of that act is not stored; the link's origin is the record, which the guide states.

## 2026-10-24 — the ban that matched every name (#160)

- **Range:** `1ac157d..9923231`
- **Pages:**
  - `guides/data-model.md` — **updated**: `domain_stopwords` carries `match_mode`, and
    `domain_ner_exclusions` matches the exact spelling; the table now says what the worker reads.
  - `guides/data-model.pt.md` — **updated**: the same two rows.
  - `guides/curate.md` — **updated**: the Stopwords tab gains the `Casamento` bullet — the PATCH, the
    two modes and why an exclusion is exact.
  - `guides/curate.pt.md` — **updated**: the same bullet.
- **Measured, not assumed.** On the reference collection the migration ran up, down and up again and
  `alembic check` reported no drift; the data decision set 9 stopwords to `EXACT` and removed the
  exact `câmara municipal de curitiba`. The live measurement on the signed #138 set went from
  **P 0.909 / R 0.920 / F1 0.915** with 13 blocked gold terms to **P 0.917 / R 0.956 / F1 0.936**
  with none; ORG recall 0.568 → 0.611, boundary 27 → 12, spurious 109 → 115.
- **Not verified, and said so.** No NER worker ran over the whole collection after the change: the
  number is the bench's `live` mode over the 122 labelled documents, not a re-extraction of the
  4,813. The screen was rendered against a copy of the collection, where flipping `alameda` to
  `TOKEN` changed both the select and the row in the database; the copy was then discarded.

## 2026-10-24 — the typology refusals have a screen (#129)

- **Range:** `9923231..8e3a903`
- **Pages:**
  - `guides/curate.md` — **updated**: the Tipologias section gains the refusal queue,
    `GET /api/v1/typologies/refusals`, the dossier's `PATCH` write, the empty state's meaning and
    the note that there is no durable "no typology" verdict; the catalogue table row names the queue
    and its reversibility.
  - `guides/curate.pt.md` — **updated**: the same paragraph and table row.
  - `guides/data-model.md` — **no-change**: the report named it for `models/governance.py`; the page
    names `llm_decision` but not its length, and the queue paragraph (`TYPOLOGY_LOW_CONFIDENCE` and
    the score it saw) is unchanged.
  - `guides/operate.md` — **no-change**: the report named it for `router.tsx`; the diff is the typology
    route's `offset` search, not the operations panel, and the typology worker paragraph already says
    the refusal is recorded with the score. The screen that settles it belongs to the curation guide.
- **Measured, not assumed.** The migration widened `llm_decision` to 100; `alembic upgrade head`
  applied it on the dev database (`scrinalia_zeroed`) and `alembic check` reports no new operations.
  The new API test pins the page to the predicate and the count, and the route to 401/200/403. The
  index was not added: on the reference collection with 3,000 descriptions available, 100 queue rows
  cost **0.5 ms** for the page with or without it; 5,000 rows cost **15.8 ms / 3.9 ms** (page/count)
  without and **18.7 / 4.8** with; 50,000 rows cost **85.6 / 15.0** without and **78.3 / 15.6** with.
  The only gain was 8.5% on the page at 50k, a queue this collection does not have.
- **Looked at, not assumed.** The screen was rendered against the dev database with three seeded
  refusals (0.39, 0.30, 0.05): the queue showed the current titles, the labels and the scores in that
  order. Selecting `Planta Arquitetônica` and clicking `Classificar` removed the row, changed the
  count from 3 to 2, wrote `typology_id=1` and `review_status=HUMAN_APPROVED` on `16124` and one
  revision. The seeded rows, the revision and the temporary account were removed afterwards, and the
  document returned to `NEEDS_REVIEW` with no typology. The empty state was rendered too, and says
  what empty means.
- **Not verified, and said so.** The index measurement is a synthetic queue over the reference
  collection, not a real worker run; no typology worker ran after the change. The page was rendered on
  the zeroed dev database's 101 documents, not on the 4,812 of the reference collection, so the
  screenshot proves the screen and the write, not a production-sized list.

## 2026-10-24 — the declared worker options are validated, published and recorded (#120)

- **Range:** `8e3a903..dbb00c8`
- **Pages:**
  - `guides/operate.md` — **updated**: "What a worker accepts" (the declared options, the two column
    options and the `AI_TEXT_COLUMNS` they are checked against, the run-only `limit`), the
    `--engine-option` flag and its row, the two doors, the five refusals, the run ledger's `options`
    and the stale row that is ignored with a note.
  - `guides/operate.pt.md` — **updated**: the same sections.
  - `guides/curate.md` — **updated**: the run panel is rendered from `declared_options` with the
    pass-through block as the only free-form one, the settings form no longer has a JSON box and
    hides `limit`, and the ledger row shows the effective options.
  - `guides/curate.pt.md` — **updated**: the same three passages.
  - `guides/data-model.md` — **updated**: `archive_worker_runs.options`, and the note that the ledger
    carries the resolved engine configuration *and* the resolved worker options.
  - `guides/data-model.pt.md` — **updated**: the same row and note.
  - `guides/install.md` — **no-change**: the report named it for `pyproject.toml`, and the only
    movement there is the release's version bump.
- **Measured, not assumed.** `uv run pytest` answers **2028 passed, 1 skipped** (the 34 new unit
  tests of `test_worker_options.py`, the 3 of the pin in `test_option_columns_pin.py`, and the new
  cases in the runner and service suites); `ruff check`/`ruff format --check` and `basedpyright`
  answer zero. `alembic upgrade head` applied `efe037349552` on the dev database and `alembic check`
  reports **no new upgrade operations**. `bun run contract` regenerated the document and the client,
  and `tsc`, ESLint and the Vite build are green.
- **The pair was measured, not asserted.** The typology benchmark and the write path now refuse the
  same spelling through the same helper: `unknown_ai_columns(["original_title", "admin_bio_historia"])`
  answers `["admin_bio_historia"]` for both, and the API's sentence names the five known columns. The
  measured default of `columns_to_extract`, resolved by the worker itself, is
  `original_title, admin_bio_history, provenance, scope_content`.
- **Looked at, not assumed.** The three screens were rendered on the dev database through a temporary
  admin account: the settings card of `typology` shows five column checkboxes, the confidence field and
  the `force` flag, **no JSON box and no `limit`**; the run panel of `ner` shows the same fields plus
  `limit`, and its opened *Repasses ao engine (avançado)* block lists `device, disable, model` as what
  the axis passes; the ledger shows a seeded run with
  `columns_to_classify=original_title,scope_content · confidence_threshold=0.4` and a row without the
  column reading "opções não registradas nesta execução". The seeded rows and the account were removed
  afterwards.
- **Not verified, and said so.** No worker was run after the change: the recorded-options path is
  proved by the integration test with a fake worker (the record of `ner` carries the resolved default
  columns and not the `None` of the signature), not by a real extraction or classification over the
  collection on this machine, and the screens were rendered over the 100 descriptions of the dev
  database rather than the reference collection. The `--engine-option` coercion is covered by unit
  tests on argument parsing, not by a run that loaded a model with an overridden `device`.

## 2026-10-24 — the SPA's request bodies are derived too (no page changed)

- **Range:** `dbb00c8..77bca6b`
- **Pages:** **none**, and that is the verdict this entry records. The change lives inside
  `apps/curator/src/api/` and `testing/unit/curator/`, and no page declares either path among its
  `sources:` — `uv run python docs/_hooks/freshness.py` answers "every page is fresh" and names
  none. What changed is a **rule file**, `.dsh/skills/curator-ui/SKILL.md`: a request body is
  derived from the model the route declares, never typed out, with the measured asymmetry beside it.
- **Why the round exists:** #93 recorded the half #88 left out. The query position fails loudly
  (an unknown filter is ignored and the screen filters by nothing); the body position fails the
  other way, because pydantic refuses a missing *required* field and silently ignores an unknown
  one. Sizing it against the checkout found **fifteen** functions typing a body by hand, not the
  thirteen the issue counted: the issue already subcounted (fourteen at `32d19f1`, the commit
  nearest its date) and `setStopwordMatch` arrived afterwards in `9923231`.
- **What the round measured.** The thirteen request models do not share one policy: ten keep
  pydantic's default (`extra="ignore"`) and three declare `extra="forbid"` —
  `SubjectExclusionRequest`, `SubjectExclusionRemovalRequest`, `ConflictPreviewRequest`. Renaming an
  optional field is silent in ten of the thirteen: `EntityMergePreviewRequest` with `new_name` →
  `new_nam` validates and the merge simply does not rename, while `MergePreviewRequest` fails only
  because its cross-field validator then finds neither source of truth — an accident, not a policy.
  The API-side question is #177.
- **Three things the issue did not know.** `SubjectExclusionRequest.source` has a `HUMAN` default,
  so the client's "required by the contract, and deliberately so" was false — the client now requires
  it by a derived `Omit`/`Required<Pick<>>`, and the comment says why. `NerExclusionRequest` is
  shared by the `POST` and the `DELETE`, whose handler reads only `data.words`, the exact smell
  `SubjectExclusionRemovalRequest` already documents — filed as #176. And
  `previewSubjectExclusions` had no caller since it was born in `32d19f1`: measured, the only unused
  export among 130, so the client function and its two response types are gone and the intent lives
  in #175.
- **Verified, and what was not.** The gate was proved by mutation, not by passing: putting one body
  back inline fails both rules, deriving a body from another route's model fails the second, and
  adding a narrowing outside the table fails the third; the file was restored byte-identical
  afterwards. `tsc`, ESLint, the Vite build, `ruff check`/`format --check` and `basedpyright` answer
  zero, and `uv run pytest testing/unit` answers **1044 passed, 1 skipped**. **Not looked at in a
  browser, and nothing to look at**: the emitted bundle is byte-identical to the pre-change one
  (`dist/assets/index-DIQDkiK4.js`, sha256
  `21ca64dc0b02571364431c9c52300079d69fc236c8d03b54a06ddc015dd0b75c`), because a type-level change
  erases at compile time — so no screen's pixels can differ, and no rendering would show the change.

## 2026-10-24 — the NER removal declares only what it reads (#176)

- **Range:** `77bca6b..2e0e9b9`
- **Pages:**
  - `guides/curate.md` — **no-change**: the page was reported stale through the contract and the
    taxonomy controller, and the paragraph it owns (*Exclusões de NER*) names the reversal as a plain
    `DELETE` that re-opens the term, never as a body. The removal's model is not described there, and
    the screen's call sends `{words: [word]}` either way, so the text still holds.
- **Why the round exists:** the `DELETE` on `/entities/ner-exclusions` took the ban's
  `NerExclusionRequest` and read only `data.words`, so a `reason` answered 200 and vanished; the
  client had narrowed it back with `Pick<NerExclusionRequest, "words">`. #176 gave the removal its
  own model, `SubjectExclusionRemovalRequest`'s twin, and the narrowing went with it.
- **What the round measured.** The contract diff is the new schema and the `$ref` of the one
  operation, nothing else: `bun run contract` emits `NerExclusionRemovalRequest` with `words` and
  `minItems: 1`, and the generated client's signature changes from the narrowing to the model.
  The behaviour is pinned by `test_remove_ner_exclusions_refuses_the_reason_the_route_ignores`
  (a `reason` is a **400**, and the service is not called) and by the table in
  `testing/unit/curator/test_api_body_shapes.py`, which now lists **three** narrowings instead of
  four. `uv run pytest testing/integration/api/controller/test_taxonomy_controller.py` answers **63
  passed** against the test database; `testing/unit/api`, `testing/unit/curator` and
  `testing/unit/docs` answer **147 passed**; `ruff check`, `ruff format --check` and `basedpyright`
  answer zero, and `tsc`/ESLint are green.
- **Not verified, and said so.** No screen was rendered: the change is a request model and a
  generated type, and the screen behind it sends the same body before and after. The API was not
  driven by hand against the reference collection either — the 400 is the integration test's client.

## 2026-10-24 — the refusal comes before the write (#175)

- **Range:** `2e0e9b9..83f7d39`
- **Pages:**
  - `guides/curate.md` — **updated**: the *Não é assunto* section said the preview route "exists as
    an API read — no screen calls it". It now describes the box asking the route as the typing
    settles (250 ms), what the two lines on the screen mean, why a partial refusal leaves the button
    enabled, and that the route takes only the terms.
  - `guides/curate.pt.md` — **updated**: the same paragraph, same structure.
- **Why the round exists:** #175. The plan route has existed since #83, and the client function that
  read it had none of the 130 callers and was deleted in #93; the screen read `blocked` from the
  write's answer instead, so the refusal arrived after the click. The route also declared the write's
  `SubjectExclusionRequest` and read only `data.words` — #176's smell in a second place, which this
  round fixed with `SubjectExclusionPreviewRequest` rather than adding a narrowing to the client.
- **What the round measured.** The contract diff is the new schema and the one operation's `$ref`.
  The behaviour is pinned by `test_the_subject_exclusion_preview_declares_only_the_terms` — the
  preview refuses a `reason`/`source` body with **400** — and by the existing dry-run test, which
  sends `{"words": [...]}` and still reads the same plan. `pytest` over the tag catalogue and the
  body-shape gate: **20 passed**; `tsc`, ESLint, `ruff check`/`format --check` and `basedpyright`
  answer zero.
- **What was rendered.** `.render/subject-exclusions-preview.png` and
  `.render/subject-exclusions-blocked.png`: the built SPA served by the API (`create_app()` mounts
  `dist`) against `scrinalia_zeroed`, with a session row inserted for the round and deleted after
  it, driven over CDP. With `capejo, vista aerea` in the box the screen reads, **before any click**,
  `1 termo(s) já estão numa categoria de assunto e não serão registrados: capejo (Mobilidade e
  Transporte)` beside `1 termo(s) serão registrados e banidos de voltar a virar tag.`, and the
  button stays enabled; with `capejo` alone only the refusal line renders and the button is
  **disabled** (CDP reported `disabled=true` and the pixels show it greyed).
- **Not verified, and said so.** No write was performed from the screen: the ban would have recorded
  a human verdict in the reference collection for the sake of a screenshot, and the write path is
  covered by the integration suite. The screen was read on `scrinalia_zeroed` only (101
  descriptions, 139 exclusions, 83 tags in drawers), not on the large collection.

## 2026-10-24 — the stamp breakdown says which ledger it counts (#150)

- **Range:** `83f7d39..55fda25`
- **Pages:**
  - `guides/operate.md` — **updated**: *What each queue means* gains the paragraph that separates the
    four numbers from `pending` — the breakdown is over the worker's whole ledger, and the reference
    collection's NER card reads 4.831 stamped against 4.813 pending, the difference being the 18
    descriptions a human approved.
  - `guides/operate.pt.md` — **updated**: the same paragraph.
  - `guides/curate.md` — **updated**: the workers screen opens four facts now, with the queue and the
    ledger apart, and the page points at the operate guide for what each one counts.
  - `guides/curate.pt.md` — **updated**: the same sentence.
- **Why the round exists:** #150. The placement read as a decomposition of the queue — "4.813 pending
  beside 0 + 1.650 + 3.181" — and the 18 units that are not pending had nowhere to be seen. #137 had
  added `stamp_breakdown` and the card rendered it under `Fila`; the number was right and the scope
  was not.
- **What the round measured.** The difference is not arithmetic in the abstract: on the collection the
  render used, `select review_status, count(*)` gives **18** `HUMAN_APPROVED` and no document without
  text in the extracted columns, so `4.831 − 18 = 4.813` is `ai_writable_documents()` doing exactly
  what it promises. The contract diff is the description of one field (`stamp_breakdown`), with the
  component untouched (the field node carries the description, not the `WorkerStampBreakdownDTO`).
- **What was rendered.** `.render/workers-150.png`: the built SPA served by the API against a **clone**
  of the large collection (`scrinalia_150`, `CREATE DATABASE ... TEMPLATE memoriacuritibana`, then
  `alembic upgrade head` — two additive migrations — dropped after the round), with a session row
  inserted and deleted for it, driven over CDP. The NER card, expanded, reads **FILA
  (DESCRIÇÕES) 4.813** with "o predicado da fila: o que a próxima execução leria. Não é o ledger do
  worker." beside **CARIMBOS (DESCRIÇÕES) 4.831** with "0 com produtor · 1.650 sem produtor
  conhecido · 3.181 sem registro — o ledger inteiro do worker, não a fila." The four facts fit one
  row at 1280px (`sm:grid-cols-2 xl:grid-cols-4`).
- **Not verified, and said so.** The card was read on the cloned collection only, and no worker was
  run: the ledger numbers are the clone's own state, not a fresh run's. The four non-stamp workers'
  `Processados` fact was not opened in pixels — the NER card is the stamp case the issue is about.

## 2026-10-24 — the clustering's columns are a read (#174)

- **Range:** `c71f3aa..5900c48`
- **Pages:**
  - `guides/curate.md` — **updated**: *Descobrir Categorias* gains the picker — the read route, why
    `final_title` is in the corpus and out of the default, and the three refusals (unknown column,
    empty list, list with `source_type=tags`).
  - `guides/curate.pt.md` — **updated**: the same paragraph.
  - `guides/operate.md` — **no-change**: the report named it through `document_repo.py`, where the
    four-column fallback became `CLUSTERING_TEXT_COLUMNS`. The value is the same four columns and the
    page never described them; what the clustering reads is the curation page's subject now.
- **Why the round exists:** #174. The route accepted `columns_to_extract` since it existed and no
  screen sent it; #93 narrowed the client to `Pick<SuggestMacroRequest, "source_type">` rather than
  advertise a knob nothing set. The other half was a second definition: the repository fell back to a
  literal list of four while `AI_TEXT_COLUMNS` has five, and an unknown name reached
  `getattr(ArchiveDocument, column)` for a **500**.
- **What the round measured.** The contract grows by one operation and one schema
  (`ClusteringColumnsResponse`, 45 lines in `schema.d.ts`). `CLUSTERING_TEXT_COLUMNS` keeps the same
  four values, so no behaviour changed for a caller that omits the field; the unit test pins that the
  difference from `AI_TEXT_COLUMNS` is exactly `final_title`. The integration tests answer **41
  passed** over the tag catalogue, the text-quality domain and the body-shape gate — including the
  400 that names `original_titel`, the 400 for `source_type=tags`, and the 400 for `[]`.
- **What was rendered.** `.render/discover-columns.png`, `.render/discover-off.png` and
  `.render/discover-send.png`: the built SPA served by the API against `scrinalia_zeroed`, with a
  session row inserted for the round and deleted after it, driven over CDP. Seen in the pixels: the
  five checkboxes with the four defaults marked `(padrão)` and `final_title` unchecked; every box
  unchecked disables *Propor Categorias* and prints `Escolha ao menos uma coluna.`; and with the five
  checked the request the screen sent was, read off the network event,
  `{"source_type":"documents","columns_to_extract":["original_title","admin_bio_history","provenance","scope_content","final_title"]}`.
- **Not verified, and said so.** The clustering itself was **not run to completion**: the browser was
  closed as soon as the request was captured, so BERTopic never answered and no proposal was seen on
  the screen. The run's use of the columns rests on the service test that already asserted
  `fetch_documents_for_clustering(columns_to_extract=...)` receives them.

## 2026-10-24 — a request body refuses what it does not know (#177)

- **Range:** `5900c48..4a8b78f`
- **Pages:**
  - `guides/operate.md` — **no-change**: the report named it through `system_schema.py`, whose two
    request models now inherit `RequestModel`. The page documents the *options* contract — a key the
    worker does not declare is refused inside `options` — and this change is about an unknown key at
    the top level of a body, which the page never said was accepted.
- **Why the round exists:** #177, with the policy the owner chose (forbid everywhere). The body
  position was loud only where a model happened to say so: 22 of the 53 bodies declared
  `extra="forbid"` and 31 kept pydantic's default, so the same stale client answered 400 on one route
  and 200 on the next.
- **What the round measured.** The generated contract is **unchanged**: `additionalProperties` was
  already absent for the 22 strict models, so Litestar never expressed the difference, and adding
  `extra="forbid"` to the other 31 emits nothing either — measured here by regenerating
  `openapi.json` and `schema.d.ts` and getting a **0-line** diff. The gate is
  `testing/unit/api/test_request_models.py`: it resolves the bodies from the **built** application
  (55 of them, exactly the names the contract points at from a `requestBody`), and fails both on a
  body model that does not forbid and on a walk that stops finding them. The full suite answers
  **2041 passed, 1 skipped**; `basedpyright`, `ruff check` and `ruff format --check` answer zero.
- **What the policy changed in behaviour, and the two tests that said otherwise.** Two calls used to
  be accepted and silently ignored: a `role` in the setup body (`test_the_client_cannot_choose_the_role`
  asserted 201 and ADMIN) and a `requested_by` in the run trigger. Both are **400** now, and the
  tests say so — the first also checks that the installation is still unconfigured after the refusal.
  A third test was added where the policy is a security property: a `changed_by` in the
  materialisation body is refused, because the author is the session's.
- **A finding, not fixed here.** `HierarchyMaterialisationRequest` exists twice: in
  `api/schemas/hierarchy_requests.py` (the body: `note`, `limit`) and in
  `domains/archive/schemas/hierarchy_schema.py` (the command: the same plus `changed_by`). The handler
  spreads the body and adds the session author into the command. They answer different questions, so
  the duplication is a name collision rather than a second definition — renaming would move a contract
  component and belongs to a round of its own.
- **Not verified, and said so.** No screen was rendered: no route changed shape and the SPA sends
  bodies derived from the contract, so the pixels cannot differ. The 53 bodies were not exercised
  against a live server one by one — the gate reads the policy, and the suite drives the routes.

## 2026-10-25 — the materialisation command has its own name (#184)

- **Range:** `4a8b78f..74a3a5c`
- **Pages:** **none changed by this round**, and the two the report named are the merge's trace:
  - `guides/curate.md` — **no-change**: the report named it through `a24154e`, the merge of the #174
    branch, whose page text was written and triaged in that round (`c71f3aa..5900c48`). No declared
    source moved after it — the change here is a class name in the domain schemas, which the page
    never prints.
  - `guides/curate.pt.md` — **no-change**: the same merge, and the translation was updated with the
    English page in the #174 round.
- **Why the round exists:** #184, the finding #177 recorded. Two models shared the name
  `HierarchyMaterialisationRequest` — the HTTP body (no author, the one the contract `$ref`s) and the
  service command (`changed_by`); the controller imported both, the second as
  `MaterialisationCommand`, and the docstrings had drifted by a word.
- **What the round measured.** The rename moved **22 references in 4 files** — the domain schema, the
  package `__init__`, the service and the controller (whose alias disappeared) — plus 12 constructions
  in the service's integration test, and **zero** lines of contract: regenerating `openapi.json` and
  `schema.d.ts` leaves both byte-identical, because the command is not bound to a route. The gate is
  `testing/unit/quality/test_model_names.py`: of the **276** pydantic models in the three schema
  packages, the duplicate was the only one, and the test fails with the two module names when one is
  reintroduced — proved by mutation (a duplicate class appended to `hierarchy_requests.py` made it
  fail; the file was restored byte-identical). Full suite **2044 passed, 1 skipped**; `basedpyright`,
  `ruff check`/`format --check` and `tsc`/ESLint green.
- **Not verified, and said so.** No screen was rendered — the rename touches no route and no generated
  type, so no pixel can differ. The materialisation routes were exercised only through their
  integration tests, not against a live server.


## 2026-10-25 — the workers leave the API (ADR 0014)

- **Range:** `74a3a5c..27063f7`
- **Pages:**
  - `adr/0014-the-workers-leave-the-api.md` — **created**
  - `adr/0004-worker-execution-from-the-api.md` — **updated** (superseded)
  - `adr/index.md` — **updated**
  - `guides/install.md` / `install.pt.md` — **updated**: the runner and the API; the network and the
    credential; the GPU host; the compose `runner` service.
  - `guides/operate.md` / `operate.pt.md` — **updated**: the runner; interrupted runs by lease; the
    queue in the ledger; the panel's runners and availability; the limits.
  - `guides/data-model.md` / `data-model.pt.md` — **updated**: the request/runner/lease columns and
    `archive_worker_runners`.
  - `README.md` — **updated**: the runner, the image and `bun run dev`.
  - `SECURITY.md` — **updated**: the runner's database reachability replaces the single-process
    bullet.
  - `guides/curate.md` / `curate.pt.md` — **no-change**: the report names them through the release's
    version declarations; the curation contract and the screens did not move — the panel's new fields
    are additive and belong to operate.
- **Why the round exists:** #42, milestone 1.6: move the workers out of the API behind a runner and a
  lease, before the retry (#43) and cancellation (#72) policies.
- **What the round measured.** Six commits: the ADR; the queue columns/table/indexes; the runner
  credential; the claim/lease/run; the API only enqueueing; the panel. The migration
  `a842f9efad08`, and `alembic check` reports no drift. Full suite **2079 passed, 1 skipped**;
  `basedpyright`, `ruff`, `tsc`, ESLint and the Vite build green. Rendered and looked at: the workers
  panel (an online runner with two capabilities, `sem runner` on the seven others, `Enfileirar
  execução`) and the run history (a live run enqueued by the panel, claimed and closed by a runner,
  showing `runner`, `sinal` and `lease`). The run was #9, `SUCCESS`, claimed **0.46 s** after the
  enqueue.
- **Not verified, and said so.** The GPU host is not this machine: the runner rendered is the CPU one
  and the CUDA path is the install guide's, not a measured run. A real remote database over
  TLS/tunnel was not exercised; the `RUNNER_DATABASE_URL`/`DB_SSLMODE` path is tested against the
  local database only. #43/#72 are vocabulary in the ADR, not code. The API with several processes was
  not run; the claim/lease tests use two runners on one database.

## 2026-10-25 — schedules and retries (ADR 0015)

- **Range:** `27063f7..692de01`
- **Pages:**
  - `adr/0015-schedules-and-retries.md` — **created**: the agenda, the scheduler, the retry and the slot.
  - `adr/index.md` — **updated**.
  - `guides/install.md` / `install.pt.md` — **updated**: the `DEFAULT_TIMEZONE` row, the scheduler process,
    the compose service.
  - `guides/operate.md` / `operate.pt.md` — **updated**: the "no scheduler" section replaced by
    "Scheduling and retries"; the agenda on `/configuracoes/workers` and `/sistema/workers`; the retry
    policy and the slot; the limits.
  - `guides/data-model.md` / `data-model.pt.md` — **updated**: `archive_worker_schedules` and the
    `attempt`/`retry_of`/`not_before` columns.
  - `README.md` — **updated**: the scheduler and the retry.
  - `AGENTS.md` — **updated**: the scheduler command and the dev script (PATCH 1.2.2, 15,998 B).
  - `.dsh/skills/workers`, `.dsh/skills/data` — **updated**: the scheduler/retry and the 34 settings.
- **Why the round exists:** #43, milestone 1.6: the scheduling and the retry ADR 0014 deferred.
- **What the round measured.** Six commits: the ADR 0015; the schedule table and the attempt columns; the
  scheduler (the advisory lock, the tick, the skip, the catch-up, the cron's DST); the retry and the
  API (the routes, the DTOs, the retry as a new row); the panel; the dev/deploy. The migration
  `b7e4c2a9f1d0`, and `alembic check` reports no drift. Full suite **2124 passed, 1 skipped**;
  `basedpyright`, `ruff`, `tsc`, ESLint and the Vite build green; `mkdocs --strict` green. Rendered and
  looked at: the agenda in `/configuracoes/workers` (the `*/1 * * * *` cron, `America/Sao_Paulo`, the
  enabled state and the next run), the **agenda** badge and fact in `/sistema/workers` (with `sem
  runner` on the seven workers the runner does not accept) and four `SCHEDULE` runs in
  `/sistema/execucoes`, claimed by `render:9055ae26`.
- **Not verified, and said so.** The retry's live path was not rendered: the render's cleaning run
  succeeds, so "tentativa 2/3" and "nova tentativa de #N" are covered by the integration tests, not by
  a screenshot. The advisory lock's standby/failover was tested with two services on one test database,
  not observed across two hosts. A GPU host or a multi-host deploy was not exercised.

## 2026-10-25 — a run can be stopped from the panel (#72)

- **Range:** `57c58fd..b84cad3`
- **Pages:**
  - `guides/operate.md` / `operate.pt.md` — **updated**: the ledger columns and the `CANCELLED`
    status, the new **Cancelling a run** section (the request, the two outcomes, the batch boundary,
    the CLI signals and the daemon's `INTERRUPTED`), the route and screen tables, the retry note and
    the limits. The trigger list now names `SCHEDULE`, which the #43 round left out.
  - `guides/data-model.md` / `data-model.pt.md` — **updated**: `cancel_requested_at`,
    `cancel_requested_by`/`_user_id` and the `CANCELLED` value on `archive_worker_runs`.
  - `guides/curate.md` / `curate.pt.md` — **updated**: the Execuções screen's one write, with the
    confirmation and the honest granularity.
  - `.dsh/skills/workers` — **updated**: the cancellation is a request, `RunControl.checkpoint`, the
    source gate, the `BaseException` choice and the CLI/daemon split.
  - `adr/0014` — **no-change**: decision 9 fixed this vocabulary and named #72; the ADR records the
    decision, and this round is its implementation.
- **Why the round exists:** #72, milestone 1.6 — the panel could start work it could not stop, and
  the only lever was `docker compose stop`.
- **What the round measured.** Four code commits: the ledger (the enum value, the two columns with
  their author link, the migration `d72c0a4b1e9f`, the DTO and the repository); the runner (the one
  `RunControl.checkpoint`, the six loop checks, the CLI signal handler, the service use case); the
  API (the route, the two codes, the generated contract); the SPA (the status mirror and the row
  action). Full suite **2146 passed, 1 skipped**; `basedpyright`, `ruff`, `tsc`, ESLint and the Vite
  build green; `alembic upgrade head` and `alembic check` report no drift; `mkdocs --strict` green.
- **What was rendered.** `.render/72-runs.png` shows the three states together: the `RUNNING`
  `embedding` row with "Cancelamento pedido em 25/10/2026, 14:05 por Cassio…", the `CANCELLED`
  `thumbnail` row, and the `QUEUED` `typology` row with **Cancelar execução…**.
  `.render/72-confirm.png` shows the inline confirmation and its sentence; `.render/72-cancelled.png`
  shows the `typology` row after the browser clicked **Confirmar cancelamento** — the POST ran
  through the real route and the row came back **Cancelada**. The `RUNNING` row was claimed by
  `render:demo` with a direct `UPDATE` (no worker process), and the request was recorded through the
  API; the scratch session row and the three runs were deleted after the round.
- **Not verified, and said so.** The batch-boundary stop of a real model run was not observed: the
  checkpoint is covered by the integration tests with a double, not by a spaCy/torch run. The CLI's
  signal handler is unit-tested as a callable, but no `SIGTERM` was delivered by the operating system
  to a process mid-batch. The daemon's `SIGTERM` → lease → `INTERRUPTED` path was not exercised.


## 2026-10-25 — the origin is a first-class object (#44)

- **Range:** `b84cad3..8e0c42f`
- **Pages:**
  - `adr/0016-the-origin-is-a-first-class-object.md` — **created**: the decision (definition in
    code + lifecycle row, `origin_code` as provenance, the `ingestion` stage in the same ledger, the
    manual entry as `PENDING_AI`, the deferred CSV and per-origin AI settings).
  - `adr/index.md`, `mkdocs.yml` — **updated**: the new ADR is linked and in the nav.
  - `guides/operate.md` / `operate.pt.md` — **updated**: ten workers with `ingestion` first, the
    origin table and screen, the manual entry, the per-origin slot and agenda, the removed
    `ACERVO_SOURCE`, the origin routes, the `origin` filter on the ledger and the `ingestion` row that
    links to the origin screen.
  - `guides/install.md` / `install.pt.md` — **updated**: the origin is a row, not a setting;
    `PUBLIC_SCRAPE_*` is the fallback for `pmc`; the migration seeds `pmc` and `manual`; the upgrade
    path is `/sistema/ingestao`.
  - `guides/data-model.md` / `data-model.pt.md` — **updated**: `ingestion_origins`, `origin_code` on
    the queue/raw/staging/archive/run ledger, `created_by` on `raw_data`, and the provenance-not-key
    rule.
  - `guides/curate.md` / `curate.pt.md` — **updated**: the `/sistema/ingestao` screen, the worker row that links to it (the generic run button cannot name an origin) and the manual
    form — data entry, not an approval; the AI queue sees the record; the operator controls are
    hidden for a curator.
  - `README.md` — **updated**: the ten worker names, the ingestion screen and the origin agenda.
  - `.env.example` — **updated**: `ACERVO_SOURCE` removed; `PUBLIC_SCRAPE_*` documented as the
    reference adapter's fallback.
  - `.dsh/skills/ingestion` — **updated**: the origin object, per-record schema, the `ingestion`
    stage and the manual origin; the old `ACERVO_SOURCE` rule removed.
  - `.dsh/skills/workers` — **updated**: the `ingestion` spec and the per-origin slot.
  - `.dsh/skills/data` — **updated**: 33 settings fields, no `ACERVO_SOURCE`, the origin is a row.
- **Why the round exists:** #44, milestone 1.6 — the origin was a parameter with one selector and no
  lifecycle, no agenda and no attribution; and the ingestion was the one stage the panel could not
  answer for.
- **What the round measured.** Full suite **2164 passed, 1 skipped**; `basedpyright` **0 errors**;
  `ruff check` and `ruff format --check` green; `tsc`, ESLint and the Vite build green;
  `alembic upgrade head` applied `44a1b2c3d4e5` and `alembic check` reports no drift;
  `mkdocs build --strict` green. The generated contract was regenerated and matches the app.
- **What was rendered.** `.render/44-ingestao.png` is the screen with the manual form and both origin
  cards; `.render/44-ingestao-config.png` is the PMC configuration panel (URLs and delay);
  `.render/44-ingestao-agenda.png` is its agenda (cron, IANA zone, save/remove);
  `.render/44-ingestao-submit.png` is a **real** submit: the form filled, the POST ran, and the
  success notice returned the manual id and "a transferência foi enfileirada". The record was staged
  and the transfer row was queued; the scratch rows and the temporary account were removed after the
  round.
- **Not verified, and said so.** No runner was online, so the queued transfer was not executed by a
  runner in the browser; the archive `PENDING_AI` and the NER queue are covered by the integration
  test (`test_manual_ingestion_stages_the_record_and_queues_the_transfer`), which runs the transfer
  directly. A real scraper execution of the `ingestion` worker against the reference site was not
  run, and the scheduler's origin tick was tested against the test database, not observed in a live
  process. The CSV import (#191) and the full manual field set (#192) are not in this change.

## 2026-10-25 — the ingestion panel stops reporting a total (#49)

- **Range:** `8e0c42f..e1362e1`
- **Pages:**
  - `guides/operate.md` / `operate.pt.md` — **updated**: the `ingestion` row in `/sistema/workers` has
    no aggregate pending/processed/failed counters — those are per origin on `/sistema/ingestao`; the
    health card reads `ingestion_origins` (active/total and each origin's label, with a link), and the
    process card labels `PUBLIC_SCRAPE_*` as the environment fallback it is. The health route and
    screen rows name the new summary.
  - `.dsh/skills/workers` — **updated**: the `ingestion` spec has no aggregate counters; the row is
    a pipeline index.
  - `.dsh/skills/observability` — **updated**: the health probe reads the origin table, not the env
    flag, and the queue stays on the ingestion screen.
- **Why the round exists:** #49 was written before `/sistema/ingestao`; #44 delivered the intent, but
  left a row whose `processed`/`failed` were record totals under an "origens" label, and a health flag
  that could say "not configured" with the origin row configured. The round repurposes #49 for those
  two truthfulness defects instead of duplicating the origin screen.
- **What the round measured.** Full suite **2167 passed, 1 skipped**; `basedpyright` 0 errors;
  `ruff check` and `ruff format --check` green; `tsc`, ESLint and the Vite build green; the API
  contract was regenerated and matches; `mkdocs build --strict` green. Rendered with the dev database
  and a temporary admin: `.render/49-health.png` shows "2 de 2 origens ativas", both labels and the
  **Abrir ingestão** link, and the process card says "fallback de coleta no .env presente";
  `.render/49-workers.png` shows the `ingestion` row with **Abrir ingestão**, no aggregate counters.
- **Not verified, and said so.** The **Abrir ingestão** link was rendered and typechecked, but was not
  followed in the browser this round; `/sistema/ingestao` itself was rendered in the #44 round. The
  health probe's database-down path is a unit test with a double, not a stopped database. No new
  migration: the table and columns are the #44 ones.

## 2026-10-25 — the description thumbnail reaches the screen (#102)

- **Range:** `89b2ec6..ed52347`
- **Pages:**
  - `adr/0017-the-thumbnail-reaches-the-browser-through-the-api.md` — **created**: the delivery
    decision (an authenticated proxy route, a `thumbnail_url` derived on the read view, 404/503 for
    the two failure states, the public route deferred to #46) and the rejected presigned, redirect
    and public-read alternatives.
  - `adr/index.md`, `mkdocs.yml` — **updated**: the new ADR is linked and in the nav.
  - `guides/curate.md` / `curate.pt.md` — **updated**: the dossier's media card, the list's 56 px
    miniature, the three states ("sem imagem", "indisponível", the image), the route and its
    `thumbnail_url`, and the public projection still carrying the raw `s3://` reference (#46).
  - `guides/operate.md` / `operate.pt.md` — **updated**: the worker writes the object; the API serves
    it on demand, so the endpoint must stay reachable from the API and allow `GetObject`.
- **Why the round exists:** #102 — the `thumbnail` worker had filled 97 of the 101 reference
  descriptions and no screen read the field; the browser cannot resolve an `s3://` URI, and the
  endpoint is the API's private one (`.env` says `http://localhost:8333`, the compose file says
  `http://host.docker.internal:9000`). The issue also asked for a documented decision between a
  presigned GET and a proxy, and for a screen that still renders when the object is gone.
- **What the round measured.** Full suite **2187 passed, 1 skipped**; `basedpyright` **0 errors**;
  `ruff check` and `ruff format --check` green; `tsc`, ESLint and the Vite build green; the API
  contract was regenerated and matches the app; `mkdocs build --strict` green. The 101 descriptions
  yield **97** with a `storage_thumbnail_uri` and **4** with neither a stored URI nor a source image;
  one object sampled in the local bucket is **384×249, 119,702 bytes, image/jpeg**.
- **What was rendered.** `.render/102-built-dossie-imagem.png` is the dossier with a real stored
  image; `.render/102-built-dossie-sem-imagem.png` is description 2731, one of the four without a
  source image; `.render/102-built-dossie-indisponivel.png` is description 1000, whose URI has no
  object in the bucket and therefore answers 404; `.render/102-built-lista.png` is the collection
  list with miniatures and the same two placeholders. All four are the **built** SPA served by the
  API at `:8000`, rendered in the headless shell at 1280×1000, with a temporary session row that was
  removed afterwards.
- **Not verified, and said so.** The bucket used for the render had 40 of the 97 objects (copied
  from the old `memoria-curitibana-bronze` volume into `meu-bucket-teste`); the other 57 answered
  404 and are represented by the unavailable state, not by a success. The 503 path is an integration
  test with a doubled reader, not a stopped endpoint observed in the browser. The mobile stack below
  `sm` was **not** rendered; the evidence there is the classes. The public route is #46 and was not
  implemented, so `PublicDocumentSummary` still publishes the raw `s3://` URI. No migration.

## 2026-10-25 — a trial before committing the collection, and the gabarito it reads (#71)

- **Range:** `984b514..06bada0`
- **Pages:**
  - `adr/0018-trials-and-the-human-gabarito.md` — **new**: a trial is a ledger row (`trial`,
    `trial_result`) that runs two to four configurations over one sample and writes no archival
    content; the gabarito is the human decision already recorded per axis — the latest
    `archive_document_revisions` row that changed `typology_id`, `curated_macro_category`,
    `origin=HUMAN`, the conflict resolution — and **never `HUMAN_APPROVED` alone**; the sample is the
    verdict set plus a seeded ai-writable sample; the comparison produces the settings write. Index
    and `mkdocs.yml` nav updated.
  - `guides/operate.md` / `operate.pt.md` — **updated**: "Comparing configurations on a sample" (the
    trial, the two populations, the save/run flow), the two new routes and the `trial` filter in the
    operations table, the `ensaio` badge and the comparison card in the screens table, and
    `trial`/`trial_result` in the run ledger.
  - `guides/data-model.md` / `data-model.pt.md` — **updated**: the `archive_worker_runs` row carries
    `trial` and `trial_result` (JSONB).
  - `.dsh/skills/workers` — **updated**: the trial is a run kind, the metric lives in the package, the
    gabarito rule, and the counter options now come from `configuration.counter_options`.
  - `guides/curate.md` — **no-change**: the hook flags it because the SPA routes and the contract it
    declares moved, but the comparison card lives on `/configuracoes/workers`, the operator screen
    the operations guide owns, and it needs `OPERATE`; no curation workflow changed.
  - `guides/install.md` — **no-change**: the runner daemon's flags and the deploy are unchanged; the
    trial is dispatched from a claimed row, not from a new installation step.
- **Why the round exists:** #70 made a classified description re-classifiable, so a configuration can
  be re-run; #71 answers the question before the run — *which configuration is better on this
  collection, and what does it cost?* The decision the issue demanded first, which screen owns the
  human verdict and how it relates to `HUMAN_APPROVED`, is in ADR 0018: the verdict is the decision the
  dossier, the tags screen or the conflicts screen already recorded; approving a record is not
  certifying its labels. The plan, the metric and the bench now share one definition
  (`domains/archive/evaluation/metrics.py`), and the worker calls the same `link_decision`.
- **What the round measured.** Full suite **2197 passed, 1 skipped** on the rebased branch (test database on 5434,
  `postgresql+psycopg2`); `basedpyright` 0 errors; `ruff check` and `ruff format --check` green; the
  contract was regenerated with `bun run contract` and the SPA's `tsc`, ESLint and Vite build are green;
  `mkdocs build --strict` green; `alembic upgrade head` applied `71a2b4c6d8e0` and `alembic check`
  reports no drift. Rendered with the headless shell over CDP: `.render/71-trial-table.png` is the
  comparison card of a finished trial (the side-by-side table, the `melhor concordância` badge and the
  disabled **Rodar no acervo inteiro**), `.render/71-ledger-ensaio.png` is the ledger row with the
  `ensaio` badge and the link back to the settings, and `.render/71-settings-trial.png` is the settings
  screen with the card in place.
- **Not verified, and said so.** The trial was **not run against a real model**: the rendered result is
  a scratch `archive_worker_runs` row (and a scratch session) inserted into the dev database and deleted
  after the round, so the numbers in the screenshot are a fixture, not a measurement of the reference
  collection; the screen's **Rodar ensaio** was not clicked. The route is covered by the controller
  test, the executor by unit tests with a fake engine, and the daemon dispatch by an integration test —
  but the real cost per document on this machine is unmeasured, and no typology preset was chosen from
  it. The comparison card's editors start from the current settings, not from the last trial's
  configurations; repeating a measured comparison means re-entering it.

## 2026-10-25 — a CSV imported without storage (#191)

- **Range:** `6cc6349..6ff7c7d`
- **Pages:**
  - `adr/0019-the-csv-import-is-parsed-in-the-browser.md` — **created**: the file never leaves the
    browser, the `csv` origin has no adapter and no storage, the map and the bounds are published by
    the API, and the answer is a per-row report. The alternatives (bucket upload, server-side text
    parse, one transfer per row, a durable import ledger, all staging fields now) and their reasons
    are recorded there.
  - `adr/index.md` — **updated**: the 0019 row.
  - `guides/curate.md` / `curate.pt.md` — **updated**: the Importação CSV card in the ingestion
    screen, the table row that now says a curator may type a record **or** import a CSV, and the
    per-row answer (accepted/duplicated/invalid, partial import, `PENDING_AI`).
  - `guides/operate.md` / `operate.pt.md` — **updated**: a "The CSV import" section beside the manual
    entry (the browser parse, the spec route, the 413, the duplicate rule, the one transfer and the
    re-import caveat), the two routes in the API table, the origins paragraph (`csv` has no adapter
    configuration) and the permissions sentence that now names both curator writes.
  - `guides/data-model.md` / `data-model.pt.md` — **updated**: `raw_data.created_by` is set by the
    form-based origins (`manual`, `csv`), and `ingestion_origins.config` says the csv origin has none.
    The Portuguese `raw_data` row had lost `origin_code` and the two author columns; the round put
    them back in step with the English table.
  - `guides/install.md` — **no-change**: the hook flags `package.json` and `sources.py`, but the
    change adds a contributor test script and an origin vocabulary, not a setting or an installation
    step; the `curator:test` command is in `CONTRIBUTING.md`, where the local checks live.
  - `.dsh/skills/ingestion/SKILL.md` — **updated**: the CSV rules (no storage, the one catalogue and
    the limits, the strict row rules, the `description_ids` staging window).
  - `CHANGELOG.md` — **updated**: the Unreleased/Added entry.
  - `mkdocs.yml` — **updated**: the ADR 0019 nav entry.
- **Why the round exists.** #191 was the CSV ingestion ADR 0016 deferred, and the issue opened with
  the constraint the design had to respect: the storage is optional, so an ingestion feature cannot
  depend on it. The choice recorded in ADR 0019 keeps the file in the browser, publishes one map and
  one set of bounds, and makes the API the authority over every row.
- **What the round measured.** Full suite **2228 passed, 1 skipped** (the test database on 5434,
  `postgresql+psycopg2`; 5433 was held by another process); `ruff check` and `ruff format --check`
  green; `basedpyright` **0 errors**; the contract was regenerated with the repository's
  `openapi.json` + `codegen` path and the SPA's `tsc`, ESLint, `bun test` (**20 pass**) and Vite build
  are green; `mkdocs build --strict` green and the documentation coverage gate **29 passed**;
  `alembic upgrade head` applied `191c5f0a7b2e` and `alembic check` reports no new operations.
  Rendered with the headless shell over CDP at 1280×1600, against the built SPA served by the API and
  a temporary session: `.render/191-preview.png` is the card with the detected headers, the preview
  table and the local duplicate warning; `.render/191-result.png` is the per-row report — 2 accepted,
  1 duplicated and 1 invalid (`A data 'banana' não foi reconhecida.`) — with the transfer enqueued.
  The two accepted rows and the queued transfer were scratch data and were deleted after the round;
  the temporary session and the sample file are gone, and the screenshots remain.
- **Not verified, and said so.** The transfer was **not run** during the render — no runner was
  attached — so the archive description reaching `PENDING_AI` was not observed in the browser; it is
  asserted by the integration test that runs `worker_archive_transfer.execute` over the imported
  rows. The **Baixar modelo** button was not clicked; `buildTemplate`/`toCsv` are covered by
  `bun test`, and the button only creates the Blob. The HTTP 413 path is a controller test with the
  service mocked, not a real oversized request. The install guide's `no-change` is a judgement from
  the diff, not from a page render.

## 2026-10-26 — the archive keeps the ISAD(G) record (#199)

- **Range:** `6ff7c7d..08b3ccb`
- **Pages:**
  - `guides/data-model.md` / `data-model.pt.md` — **updated**: `staging_documents` gains
    `date_expression` and the archive gains the full ISAD(G) text set plus `parent_reference_code`,
    `date_expression` and `original_url`; the paragraph explains why the spelling travels beside the
    parsed date and why the declared parent is a column now.
  - `guides/curate.md` / `curate.pt.md` — **updated**: the description tab grouped in the norm's
    seven areas, the whole record editable, the two evidence fields shown and not edited, the
    language select that keeps a value the catalogue does not know, the pending parent, and the
    digital object card with the disabled control pointing at #198.
  - `guides/operate.md` / `operate.pt.md` — **no-change**: the round changed the archive and the
    dossier, not the ingestion screen; the manual form still ships nine fields, and the sentence that
    says the rest is #192 is still true.
  - `guides/install.md` — **no-change**: no setting moved; the language catalogue is code, not a new
    environment variable.
  - `adr/` — **no-change**: no decision here is architectural enough for an ADR. The columns are
    additive, and the language catalogue becoming a table is the facet issue's decision; the module
    docstring and the issue record the reasoning.
- **Why the round exists.** #192 expands the manual form, and the archive could not store what the
  form would ask: the transfer copied 14 of the 33 content fields the staging transform parses. The
  round closes the store first, so the form grows against a table that exists, and so the dossier can
  finally show the record it claims to own.
- **What the round measured.** Full suite **2238 passed, 1 skipped** (the test database on 5434,
  `postgresql+psycopg2`; 5433 is held by another process); `ruff check` and `ruff format --check`
  green; `basedpyright` **0 errors**; the contract regenerated with the repository's `openapi.json` +
  `codegen` path, and the SPA's `tsc`, ESLint and Vite build green; `mkdocs build --strict` green and
  the documentation coverage gate **29 passed**; `alembic upgrade head` applied `e3084fbf75ba` and
  `alembic check` reports no new operations. The backfill was measured on the dev database
  (`scrinalia_zeroed`): **101** archive rows against **100** staging rows, so the migration filled
  **100** descriptions and left **1** empty (no staging row), and `date_expression` is **0** by design,
  because the staging column did not exist when those rows were parsed. Rendered with the headless
  shell over CDP at 1280×1600 against the Vite dev server and the API: `.render/199-dossier-top.png`
  is 3.1 (level, typology, reference code, date, dimension and support, the parent named from the
  branch) and 3.2 with the source link; `.render/199-dossier-mid.png` is 3.3 and 3.4, where the
  language select shows **"Português Brasil (fora do catálogo)"** — the scraped spelling, kept
  instead of erased; `.render/199-dossier-bottom.png` is 3.5 to 3.7, the diffusion flag, the disabled
  **Objeto digital** control with the one sentence, and the save bar. The temporary render account and
  its session were deleted after the round, and the browser profile and driver are gone.
- **Not verified, and said so.** The transfer was **not run** over the collection, so the CDC re-read
  and the AI re-queue that follow the hash change were not observed: the round-trip is the integration
  test that stages a record with every field and asserts every column. No field was **saved** through
  the dossier in the browser; the write path is the same `PATCH` covered by the curation test, and
  what the render proves is that the controls exist, are bound to the stored values and render in the
  right area. The language select was seen with an unknown value only; the known-value options come
  from the same `GET /api/v1/languages` list the route test pins.

## 2026-10-26 — the manual entry covers the whole record (#192)

- **Range:** `08b3ccb..33217f7`
- **Pages:**
  - `guides/operate.md` / `operate.pt.md` — **updated**: the manual entry has a screen of its own at
    `/sistema/ingestao/nova`, typed in the norm's areas; the three behaviours worth knowing (the date
    is text with the language grammar, the level and the language are selects, the digital object
    control is disabled until #198) replace the paragraph that said the form shipped the essential
    fields.
  - `guides/curate.md` / `curate.pt.md` — **updated**: the screens table gains the new row, and the
    ingestion section says the card opens the form instead of embedding it.
  - `guides/data-model.md` / `data-model.pt.md` — **no-change**: the round writes the same columns
    the archive gained in #199; nothing new in the schema.
  - `guides/install.md` — **no-change**: no setting moved, and the language catalogue is code, not a
    variable.
  - `adr/` — **no-change**: this is the form catching up with a contract that already existed.
- **Why the round exists.** #199 made the archive store the whole ISAD(G) record; the form was the
  last surface that still spoke a subset, and the CSV import had to grow with it or the file and the
  form would accept different vocabularies (ADR 0019 pins the equality).
- **What the round measured.** Full suite **2244 passed, 1 skipped** against the test database on
  5434; `ruff check` and `ruff format --check` green; `basedpyright` **0 errors**; the contract
  regenerated (31 fields in `ManualIngestionRequest`, `attachment_link` gone, the result carrying the
  parsed date); the SPA's `tsc`, ESLint and Vite build green; `mkdocs build --strict` green and the
  documentation coverage gate **29 passed**, including the new screen. Rendered with the headless
  shell over CDP at 1280×1600 against the Vite dev server and the API:
  `.render/192-form-top.png` is the identity area open — title, level, parent, reference code, the
  **text** date with its placeholder and help, dimension and support — with the six other areas
  collapsed, the disabled **Objeto digital** control and the submit disabled while the title is
  empty; `.render/192-form-area.png` is 3.4 expanded with the language select and the help under each
  control; `.render/192-ingestion.png` is the ingestion screen with the **Entrada manual** card
  reduced to the explanation and the **Nova descrição** button, the CSV card and the origin cards
  below. The temporary render account and its sessions were deleted, and the browser profile and
  driver are gone.
- **Not verified, and said so.** Nothing was **submitted** through the browser: the write path is the
  integration test that stages a record with every field and asserts every column, and what the
  render proves is that the controls exist, are bound and sit in the right area. The
  `requires_parent` warning was not triggered (no rung that requires a parent was selected in the
  render); it is a conditional in the same screen. The CSV card was rendered but not re-imported with
  the wider template: the map and the caps are the same catalogue the spec publishes, covered by
  `test_csv_import.py` and by the equality pin.

## 2026-10-26 — one spelling per language (#203)

- **Range:** `e9f0062..8660c6f`
- **Pages:**
  - `guides/data-model.md` / `data-model.pt.md` — **updated**: `language_name` holds the catalogue's
    spelling, the fold happens at the transfer with the variants declared as aliases, and a language
    the catalogue does not know is kept as the source wrote it; `staging_documents` keeps the
    declared text.
  - `guides/curate.md` / `curate.pt.md` — **updated**: the dossier's select reads the catalogued name
    (a variant is folded before it arrives), and the `(fora do catálogo)` marker is now only for a
    language the catalogue has never heard of.
  - `guides/operate.md` / `operate.pt.md` — **no-change**: the manual form already sent a catalogue
    name; the fold is about values arriving from the origins and from the past.
  - `adr/` — **no-change**: it is the catalogue #199 created, given the normalisation every closed
    catalogue in this codebase has.
- **Why the round exists.** The render that closed #199 measured the collection: `Português Brasil`
  in 78 descriptions and `Português/Brasil` in 22, both shown as unknown because the dossier compares
  strings and the catalogue says `Português`. Keeping the source's text is the right default; two
  spellings of one language in a closed list is not.
- **What the round measured.** Full suite **2270 passed, 1 skipped** against the test database on
  5434; `ruff check` and `ruff format --check` green; `basedpyright` **0 errors**; `mkdocs build
  --strict` green and the documentation coverage gate **29 passed**; `alembic upgrade head` applied
  `6c46426b048a` and `alembic check` reports no new operations. On the dev database the migration
  folded **100** rows in `staging_documents` and **100** in `archive_documents` (the collection has
  101 descriptions, one of them with no language), and the two spellings became one:
  `Português 100`, `NULL 1`. Rendered with the headless shell over CDP at 1280×1600 against the Vite
  dev server and the API: `.render/203-language.png` is the dossier's 3.4 area with the **Idioma**
  select reading `Português` — the same record that showed `Português Brasil (fora do catálogo)`
  before the fold. The temporary render account and its sessions were deleted, and the browser
  profile and driver are gone.
- **Not verified, and said so.** The fold was not exercised through a **new scrape**: the transfer
  path is covered by the integration test that stages `Português/Brasil` and asserts the archive's
  `Português` while staging keeps the declared text. The downgrade is a documented no-op and was not
  run, because it cannot restore the spelling — the fold is lossy by design.

## 2026-10-26 — the entry screen moves to the Acervo (#205)

- **Range:** `8660c6f..35d11cb`
- **Pages:**
  - `guides/curate.md` / `curate.pt.md` — **updated**: *Nova descrição* is `/acervo/nova`, the first
    entry of the *Acervo* menu, with a section of its own: the **Digitar** and **Importar CSV** tabs
    (the mode travels in `?modo=csv`), the destination said once, and the redirect from
    `/sistema/ingestao/nova`. The *Ingestão* section loses the two cards and says the curator reads
    the origins read-only.
  - `guides/operate.md` / `operate.pt.md` — **updated**: the manual entry is the **Digitar** tab and
    the CSV is the **Importar CSV** tab, both at `/acervo/nova`; `/sistema/ingestao` is origins only,
    and its `CURATE` card now buys the status read, not a curator write.
  - `guides/install.md` / `install.pt.md` — **updated**: after the migration `/sistema/ingestao`
    configures the origins and `/acervo/nova` is where a description is typed or imported.
  - `guides/data-model.md` / `data-model.pt.md` — **no-change**: no table or column moved; the
    staging and transfer paths are the same.
  - `adr/` — **no-change**: the API and the pipeline are untouched. This is where a screen lives, not
    an architecture decision.
- **Freshness.** Before the round the hook named `guides/curate.md` (the conflict tabs, #220) and
  `guides/install.md` (the 1.6.0 version bump). Both were read; the conflict screen was already
  described as tabs, the version is not a fact the install guide stores, and the updates above are
  what closes the range.
- **Why the round exists.** #205 moved the two input paths of the collection out of the ingestion
  configuration page: "Nova descrição" was the last step of Configurações -> Operação -> Ingestão,
  and the CSV import lived as a second card on a page about origins. The screen creates the object
  the Acervo lists, so it now lives there, with the two input shapes as tabs.
- **What the round measured.** Full suite **2270 passed, 1 skipped** against the test database on
  5434 (`postgresql+psycopg2`; 5433 is held by another process and its `test_user` refused the
  password); `ruff check` and `ruff format` green and `basedpyright` **0 errors** through the commit
  hook; `bun run --cwd apps/curator typecheck`, `lint` and `build` green; `bun test` **20 pass**;
  `testing/unit/curator` and `testing/unit/docs` **32 passed**; `mkdocs build --strict` green; no
  API change and no contract regeneration. Rendered with the headless shell over CDP at 1280×1600
  against the Vite dev server and the API: `.render/205-digitar.png` is `/acervo/nova` with the menu
  entry and the form; `.render/205-csv.png` is `?modo=csv`; `.render/205-csv-preview.png` is a sample
  CSV mapped header by header with one invalid row before any submit; `.render/205-ingestao.png` is
  the origins page with no entry cards. The CDP probe switched tabs to `/acervo/nova?modo=csv`, kept
  a typed draft across the round trip, and landed `/sistema/ingestao/nova` on `/acervo/nova`. The
  temporary session row was deleted and the driver and profile removed.
- **Not verified, and said so.** Nothing was **submitted** through either tab: the manual and CSV
  writes are the integration tests, and the render proves the screen, the tabs, the mapping preview
  and the redirect. The permission hiding was not exercised with a curator or viewer account — the
  render used the administrator — so the mirror is `permissions.ts` and the API guard; the final
  permission of the origins page, and whether it needs a read-only mode, is #206's decision.

## 2026-10-26 — the origins page becomes configuration (#206)

- **Range:** `5da49c6..479e459`
- **Pages:**
  - `guides/operate.md` / `operate.pt.md` — **updated**: the screen is *Origens* and has two
    sections: the configured sources (add picker, configuration, agenda, **Desativar/Ativar**,
    **Enfileirar execução**, the effective-configuration summary) and the **Entradas** (manual/CSV
    read-only, with the link to `/acervo/nova`). The page is `OPERATE`, the picker is the existing
    `PATCH`, pausing keeps the row and the agenda, a fresh install starts empty, and the health probe
    counts only the configurable origins.
  - `guides/curate.md` / `curate.pt.md` — **updated**: *Ingestão* becomes *Origens* in the *Sistema*
    table and section; the page stops being the "operator only" exception (the card is `OPERATE`, the
    read routes stay authenticated), and the entry paths remain under *Nova descrição* in the Acervo.
  - `guides/install.md` / `install.pt.md` — **updated**: a fresh installation has no configured
    source; the operator adds the `pmc` definition from the picker, and the `PUBLIC_SCRAPE_*` values
    are that adapter's fallback when the fields are empty.
  - `guides/data-model.md` / `data-model.pt.md` — **no-change**: the migration is data (a row is
    deleted when it is still the seed); no column or index moved.
  - `adr/` — **no-change**: the origin is still a definition plus a row (ADR 0016); the page now
    models the distinction instead of changing it.
- **Freshness.** The previous floor ended at the #205 feature commit, whose content the squash
  `5da49c6` carries; this round read the merged pages again and the #206 updates are what closes the
  range from `5da49c6`.
- **Why the round exists.** #206: after #205 removed the entry cards, the origins page still rendered
  every definition as a card, so "never configured" and "paused" looked the same, `manual`/`csv`
  appeared as sources, and the empty state was unreachable. The page now reads the rows, offers the
  definitions without one, and has a lifecycle.
- **What the round measured.** Full suite **2275 passed, 1 skipped** against the test database on
  5434 (`postgresql+psycopg2`); `ruff check`, `ruff format` and `basedpyright` green through the
  commit hook; the SPA's `tsc`, ESLint and Vite build green; `bun test` **20 pass**;
  `testing/unit/curator` and `testing/unit/docs` **53 passed**; `mkdocs build --strict` green; the
  contract regenerated (the additive `configurable` and `available`); `alembic upgrade head` applied
  `f1090f825a94` against the dev database (the `pmc` row kept: it has provenance) and against a fresh
  scratch database (the `pmc` row deleted; `manual` and `csv` kept), and `alembic check` reports no
  new operations. Rendered with the headless shell over CDP at 1280×1600 against the Vite dev server
  and an API on the scratch database: `.render/206-empty.png` is the empty *Origens* section with
  **Adicionar origem** and the two read-only **Entradas**; `.render/206-picker.png` is the picker
  offering the PMC definition; `.render/206-added.png` is the card active with the effective
  configuration (`Espera entre requisições (s): 0.5`) and the add action gone; `.render/206-paused.png`
  is the same card paused, with **Ativar** and "0 ativas"; `.render/206-health.png` is the health
  panel showing **0 de 1 origens ativas**, only PMC, and **Abrir origens**. The CDP probe clicked the
  add, the activation and the pause; the scratch database and its session were dropped after the
  round, and the driver and profile removed.
- **Not verified, and said so.** The permission hiding was not exercised with a curator or viewer
  account — the render used the administrator — so the read-only direct URL is the `permissions.ts`
  mirror plus the API guard. The manual/CSV entries are read-only by design, so their pause/re-enable
  has no control on the page (the `PATCH` remains) and was not exercised through the UI. The
  migration's downgrade is a documented no-op and was not run; the verification of the deletion is
  the fresh scratch database above, and the preservation is the dev database. Only one definition
  (`pmc`) is available today, so the picker was not exercised with several entries; the retired-code
  row is out of scope and is ignored by both the page and the probe.

## 2026-10-26 — one operations screen for the panel and the ledger (#207)

- **Range:** `f6efb38..1c96177`
- **Pages:**
  - `guides/curate.md` — **updated**: *Workers de IA* became *Workers e execuções*, one screen with
    two tabs in the URL (*Painel* and *Execuções*). The screen table merges the two rows, the section
    says the last run links to the filtered ledger and that the old path redirects, and the
    Configurações tab table drops the Execuções card.
  - `guides/curate.pt.md` — **updated**: the translation of the same three places.
  - `guides/operate.md` — **updated**: the SPA table merges `/sistema/workers` and
    `/sistema/execucoes` into one row (the two tabs, the last-run link, the redirect); the polling
    paragraph says only the active tab is mounted, and the cancel section names the tab.
  - `guides/operate.pt.md` — **updated**: the same three places.
  - `adr/0016-the-origin-is-a-first-class-object.md` — **updated**: the ingestion is seen in the
    execution ledger at `/sistema/workers`, not in a `/sistema/execucoes` screen; the object, its row
    and its route are unchanged.
  - `adr/0018-trials-and-the-human-gabarito.md` — **updated**: the trial is distinguishable in the
    execution ledger (the *Execuções* tab); the trial semantics are unchanged.
  - `guides/data-model.md` / `data-model.pt.md` — **no-change**: no table, column or index moved.
  - `guides/install.md` / `install.pt.md` — **no-change**: no setting or command changed.
- **Why the round exists.** The run-check loop crossed three screens and three URLs: the panel
  enqueued and showed the last run as plain text, and the ledger was a second door. #207 makes them
  one route with the tab in the URL, links the last run to the ledger filtered by its worker and with
  the exact row highlighted, and keeps `/sistema/execucoes` redirecting there with the search
  preserved. The configuration stays a screen of its own (#53).
- **What the round measured.** `bun run --cwd apps/curator typecheck` and `lint` green; the Vite
  build green (2117 modules); `pytest testing/unit/curator testing/unit/docs` **53 passed**; the
  commit hook ran ruff, ruff-format and basedpyright green; `mkdocs build --strict` green. Rendered
  with the headless shell over CDP at 1280×1500 against the Vite dev server and an API on a scratch
  database (`scrinalia_render_207`, dropped after): `207-panel.png` is the heading *Workers e
  execuções* with the two tabs, the runners card and the ten workers; `207-panel-enqueued.png` is the
  panel after one run, with "Execução #1 enfileirada; ver no ledger" and the same link under *Última
  execução*; `207-ledger.png` is the *Execuções* tab with the worker filter set and the run row
  ringed; `207-settings-operacao.png` is the landing's *Operação* tab with four cards and no
  *Execuções* card. The link's href was `/sistema/workers?aba=execucoes&worker=transfer&run=1`, and
  clicking it landed on that URL with exactly **1** highlighted row. `/sistema/execucoes?worker=transfer&run=1`
  redirected to `/sistema/workers?worker=transfer&run=1&aba=execucoes`. Clicking the tab bar itself
  moved `?aba=execucoes&worker=transfer&run=1` to `?aba=painel&worker=transfer` and back to
  `?aba=execucoes&worker=transfer`: the filter survives, and `run` is dropped by a change that is not
  itself.
- **Not verified, and said so.** The permission mirror was not exercised with a curator or viewer
  account — the render used the administrator, so the read-only direct URL is the `permissions.ts`
  mirror plus the API guard, unchanged by this round. The redirect was exercised with `worker` and
  `run` only, not with `status`, `origin`, `fingerprint` or `offset`; it carries the whole search
  object and the validator is the same one the ledger reads. The polling cadence was not measured
  over time: the evidence that only one tab polls is structural (only the active tab is mounted),
  not a stopwatch. The ledger was rendered with one queued run, so the rich row (trial, retry,
  cancellation note) is the existing screen's behaviour, not this round's.

## 2026-10-27 — one hint element for the explanations that do not deserve a paragraph (#208)

- **Range:** `1c96177..7843d9e`
- **Pages:**
  - `guides/curate.md` — **no-change**: the routes, writes and flows the guide documents did not
    move. The new `Hint` only changes how a secondary explanation is revealed on three screens —
    the conflict threshold, the CSV column badge and the worker run/effective configuration — and
    the guide never described those help affordances, only the actions they sit beside.
  - `guides/curate.pt.md` — **no-change**: the same translation, for the same reason.
  - `guides/operate.md` — **no-change**: `WorkersPanel.tsx` moved only to place the existing
    explanations behind the shared hint; the other source in the range is the Dependabot bump of
    `astral-sh/setup-uv` in `.github/workflows/ci.yml`, which changes no command, probe or worker
    behaviour the operator guide describes.
  - `guides/operate.pt.md` — **no-change**: the same two sources, the same reason.
- **Why the round exists.** The same second sentence was rendered four ways and chosen per screen,
  with the native `title` as the "discreet" default: hover-only, after a delay, never on focus,
  absent on touch, and unreliable for assistive technology. #208 adds one `Hint` primitive — a real
  button with `aria-describedby` and a `role="tooltip"` panel whose text stays in the DOM while
  closed — and migrates the first three places. `Field.info` sits outside the `<label>`, because a
  button inside a label is invalid HTML and pollutes the input's accessible name. `Tabs` uses the
  primitive through `asChild`, so the tab itself is the trigger and the interim `title` plus
  `sr-only` text from #220 is gone. The rule lives in the `curator-ui` skill.
- **What the round measured.** `bun run --cwd apps/curator typecheck`, `lint` and `build` green
  (2118 modules); `bun test` **26 pass** (20 CSV + 6 hint); `pytest testing/unit/curator` **24
  passed**; `pre-commit run --all-files` green. Rendered at 1440×900 with the headless shell over
  CDP against the Vite dev server and the dev API, with a disposable session row deleted after the
  round: `208-conflicts-hint.png` is the threshold tooltip open with the focus on its button,
  `208-conflicts-escape.png` is the same panel closed after Escape while the button keeps focus,
  `208-tab-hint.png` is the *Pendentes* tab description from the tab itself,
  `208-workers-run.png` is the run-button explanation, `208-workers-config.png` is the effective
  configuration hint (and what caught the inherited `uppercase` before it shipped), and
  `208-csv-badge.png` is the column badge after a real file was set on the CSV input. The page's
  tooltip state was `open` on focus and `closed` after Escape; the text was read back from the
  described panel, not assumed from the screenshot.
- **Not verified, and said so.** The pointer hover was driven through the DOM test and not with a
  physical mouse over the rendered screen; touch was exercised as a click in `happy-dom`, not on a
  touch device. The other `title` attributes remain (180 in `src`, three fewer than before this
  round), because the issue retires the pattern as uses migrate, not in one sweep. The tab hints remain inside the `tablist` in the accessibility tree as non-focusable
  tooltip nodes; the tabs themselves are still the owned elements and the described text is read on
  focus. No colour token, route, schema or contract changed.

## 2026-10-27 — the copy sweep reaches the rest of the interface

- **Range:** `b75d74e..7e9a5b3`
- **Pages:**
  - `guides/curate.md` — **updated**: the sweep renamed two screens the guide names by label —
    `Excluídas` → `Histórico de exclusões`, `Nova descrição` → `Nova Descrição` — and the two purge
    panels (`Ledger das purgas` → `Registro das purgas`, `Ledger dos expurgos` → `Histórico de
    expurgos`). A reader sent to `Acervo › Excluídas` would not find the entry. No route, write or
    flow changed.
  - `guides/curate.pt.md` — **updated**: the same four names, in the translation.
  - `guides/install.md` — **updated**: the backup section quotes the deletion screen by name and
    calls it a trail; it is `Histórico de exclusões`, and it is a record. What the section explains
    did not move: the snapshot row, no restore, a node with children refused.
  - `guides/install.pt.md` — **updated**: the same paragraph, same reason.
  - `guides/operate.md` — **no-change**: its only moved source is `SystemHealthRoute.tsx`, whose
    copy said `dimensions` and `NER/parser` for the effective configuration the page already
    describes. The page documents runs, queues, retries and the worker catalogue, and it names
    `ledger` as the append-only table, not as a panel — the sweep renamed the screens, not the
    mechanism.
  - `guides/operate.pt.md` — **no-change**: the same source, the same reason.
- **Why the round exists.** The first copy pass covered nine files; the second swept the remaining
  fifty-three (commit `7e9a5b3`). It replaced the system's vocabulary with the task — `ledger` →
  histórico, `staging`/AI queue out, rule kinds out of caps, `Engine` → `Motor` — and corrected
  three sentences that were false rather than technical: the anomaly empty state, the "sem
  categoria" badge, and the cleaning-rule preview's sample count. `worker` stays where it names the
  operations object, which is the exception the `curator-ui` skill now records (`a0655d4`).
- **What the round measured.** `bun run --cwd apps/curator typecheck`, `lint` and `test` green
  (26 pass); `pytest testing/unit/curator testing/unit/docs` **53 passed** (the copy gate included);
  `basedpyright` green on both commits through the pre-commit hook; `freshness.py` reports these
  three pages and no other.
- **Not verified, and said so.** No screen was rendered for this round: the evidence is the four
  gates above and the diff, not pixels. The pages quote labels, not behaviour, and no route, schema
  or contract changed.

## 2026-10-27 — the second copy read, and the screen it renamed

- **Range:** `7e9a5b3..0876ead`
- **Pages:**
  - `guides/curate.md` — **updated**: the copy pass renamed `/entidades/excecoes` from "Exclusões de
    NER" to "Remover de Entidades", and the guide quotes that label in the screen table and in the
    section heading. No route, write or flow changed.
  - `guides/curate.pt.md` — **updated**: the same two names, in the translation.
  - `guides/install.md` — **no-change**: its only moved source in the range is `lib/screens.ts`, and
    the install guide names neither the Tags screen nor this one; what moved there is the Tags
    hint/description and two screen descriptions.
  - `guides/install.pt.md` — **no-change**: the same source, the same reason.
- **Why the round exists.** A second, closer copy read over the subject, entity and dossier screens
  (`8b3acfc`) plus the correction it made necessary (`0876ead`): the entities list still linked to
  the old label, so the list and its destination named the same screen two ways. The pass also
  reopened the retired-word gate, which caught `apagar` and `unificação` and required the canon's
  `Excluir` and `Mesclagem` again — and a stray double quote in one JSX text node, which is also
  what hid that node from the scan.
- **What the round measured.** `tsc`, ESLint, 26 bun tests and 24 pytest for the copy commit;
  `ruff check`, `ruff format --check`, `basedpyright`, `bun run contract` (no drift),
  `alembic check` (no drift) and `mkdocs build --strict` for this round. `freshness.py` reported
  these two pages and no other.
- **Not verified, and said so.** No screen was rendered: the evidence is the gates and the diff.

## 2026-10-28 — the plan becomes the tree it already was

- **Range:** `ba1fb02..8f891d8`
- **Pages:**
  - `guides/curate.md` — **updated**: the plan section now describes the rungs as the tree
    `parent_code` implies, the leading box that closes a whole branch and states the hidden rungs
    and decisions, the filter that keeps a match's ancestors and branch, and the URL that records
    the closed roots. No route, write or undo changed.
  - `guides/curate.pt.md` — **updated**: the same paragraph in the translation.
- **Why the round exists.** #233 replaced one flat list indented by `plan.depth` with nested lists
  and two pure functions (`buildPlanTree`, `planRows`); a collapsed branch now hides its subtree
  without unmounting it, so an open decision body and anything typed in its form survive. The
  status filter moved to the client because a tab fetched alone has no ancestors to draw.
- **What the round measured.** `tsc`, ESLint, the Vite build, 47 bun tests (18 new) and 25 pytest
  (the copy gate) on the code commit; the full suite ran against the test database on port 5434
  (2292 passed, 1 skipped). The screen was rendered against the real 41-rung catalogue with the
  headless shell, and 29 CDP checks covered collapse/expand, the hidden counts, the status/flag/code
  filters, forced ancestors, the URL, and the two global controls. `Recolher os decididos` was not
  clicked against a real fully decided branch (the dev catalogue has none); its set is pinned by
  three pure tests. The depth-cap title above six levels was not observed either: the deepest
  rendered branch is five levels below the root.
- **Not verified, and said so.** The API and the SPA ran against the development database; the
  admin password was reset for the render and restored afterwards, and the full suite used the test
  database, not the development one.

## 2026-10-28 — the access points are chips, and the string is read before it is written

- **Range:** `8f891d8..c15060d`
- **Pages:**
  - `guides/curate.md` — **updated**: the Nova Descrição section now says the access points are chips
    over the catalogue, that the type-ahead picks an existing spelling and *Adicionar* keeps the
    archivist's, and that the summary under the control names what the transfer will discard, create
    or map to a synonym. It names `POST /api/v1/taxonomy/tags/preview` as the read behind the
    summary and says the preview removes nothing.
  - `guides/curate.pt.md` — **updated**: the same paragraph in the translation.
  - `guides/data-model.md` — **no-change**: the repository gained two read-only lookups
    (`get_tag_identities_by_names`/`by_ids`) over existing columns and the unique normalized-name
    index; no table, column, constraint or relationship changed, so the model page is still true.
  - `guides/data-model.pt.md` — **no-change**: the English page it translates did not change.
- **Why the round exists.** #229: the creation form asked for one comma-separated string and the
  transfer then lowercased it, dropped banned, short and long terms and created unknown spellings,
  with no message. The field is now a chip editor over the catalogue; the explicit *Adicionar* keeps
  a new term, and one read-only summary says what the transfer will do with the whole string. The
  wire is still `indexing_points: str | None`; the CSV column and the scraper are untouched, and the
  transfer remains the only writer.
- **What the round measured.** `ruff check`, `ruff format --check`, `basedpyright`, 2310 pytest
  passed and 1 skipped against the test database on port 5434, 61 bun tests, `tsc`, ESLint,
  `bun run contract` (the new route), `alembic check`, the docs coverage suite and `mkdocs build
  --strict`. The screen was rendered against the development database with the headless shell: the
  old free-text field, then the new chips with an existing tag, a synonym, a banned term and a new
  term, plus the type-ahead open. The first render showed the input's own focus outline around the
  text field only; the ring was moved to the chips box and the screen re-rendered. The warning line
  of the summary was moved first after the first render.
- **Not verified, and said so.** The render used the development database; the admin password was
  reset for it and its hash restored afterwards, and the render sessions were deleted. The summary's
  copy was observed on the development catalogue; the blocked, synonym and new states are pinned by
  the API and component tests, not by a catalogue built for the screenshot. The CSV import was not
  re-rendered, because its column, map and copy are unchanged.


## 2026-10-28 — the producer field copies a name, it does not link

- **Range:** `ee24d79..6ba1d64`
- **Pages:**
  - `guides/curate.md` — **updated**: the Nova Descrição section now describes `Produtor(es)` as a
    name autocomplete over the entity catalogue: the fragment between separators that a pick
    replaces, the verbatim copy (the catalogue stores names lowercased), the deliberate absence of an
    entity-type filter, and the sentence that a copied name is not a link.
  - `guides/curate.pt.md` — **updated**: the same paragraph in the translation.
- **Why the round exists.** #230 was scoped down after the measurement that the producer variants in
  this database are an ingestion shape (7 spellings for 5 creators, all 101 descriptions from the
  `pmc` origin) and that the entity axis has no creator role. What shipped is the convenience half:
  the copy. The relation — description ↔ creator, the entry normalisation, the list filter and a
  producer worker — moved to #242, in the *Future Ideas* milestone.
- **What the round measured.** `tsc`, ESLint, 72 bun tests (11 new in
  `apps/curator/tests/entityNameField.test.tsx`) and 25 pytest in `testing/unit/curator` (the copy
  and manual-form gates). The screen was rendered against the development database with the headless
  shell: the creation form with the 3.2 Contexto area open and the dropdown for "prefeitura" (two
  entities, `ORG · 23 descrições` and `LOC · 1 descrição`), the value after the pick with the caret
  at its end, and the dossier of description 391, where typing ", gui" after the existing
  "Prefeitura Municipal de Curitiba" searched only the fragment and the pick replaced only it. The
  field sits inside the collapsed area on the creation screen, which is the form's default and not a
  defect: the screenshot of the form before opening it shows no producer control, and that is the
  screen the archivist meets.
- **An observation, not a fix.** "gui" returned "rua assungui" (`LOC`, 3 descriptions) before "guido
  ghilardi" (`PER`, 1): the endpoint orders by usage, which the dossier's entity picker already
  inherited. Nothing in this change touches that ordering.
- **Not verified, and said so.** The dossier pick was checked in the draft and the browser closed
  without saving, so the write path is the existing one and was not exercised. The suggestion list was
  not seen against an empty catalogue. Nothing in the CSV import, the public DTO or the API changed,
  and none of them was re-rendered.

## 2026-10-28 — the blocked spellings are a screen

- **Range:** `263d936..67f00ad`
- **Pages:**
  - `guides/curate.md` — **updated**: the Assuntos table gains `Grafias bloqueadas —
    /assuntos/grafias` and Tags loses the banned terms; `#### Stopwords` moves out of the Tags
    section and becomes its own `###` section, with the two objects stated (meaning × spelling), the
    reciprocal link and the `?aba=stopwords` redirect; the Similaridade, Classificar and *Não é
    assunto* paragraphs now name the screen instead of the tab, and the *Não é assunto* section says
    which of the two each one is.
  - `guides/curate.pt.md` — **updated**: the same translation, in the SPA's vocabulary.
  - `guides/data-model.md` — **no-change** beyond the name: two sentences said "the Stopwords
    screen" for `save_stopwords`, and the screen is now `Grafias bloqueadas`; the table, the columns
    and the ledger paragraphs still hold.
  - `guides/data-model.pt.md` — **updated**: the same two references.
- **Why the round exists.** #232 found two screens sharing a vocabulary, a dataset and a verb, with
  the only destructive write of the axis two clicks under a page that never mentioned it. The fix
  moved the blocked spellings to their own screen, renamed the copy at the object (a *grafia*, not a
  term), and made the two screens name each other.
- **What the round measured.** `tsc`, ESLint, the Vite build, 72 bun tests, `basedpyright` (0 errors)
  and 56 pytest across `testing/unit/curator` (27, including the three new copy rules) and
  `testing/unit/docs` (29). The screens were rendered against `scrinalia_render` with the headless
  shell: `/assuntos/grafias` with 208 blocked spellings in three axes, a ban whose origin is a
  verdict (`veio de “não é assunto”`) carrying the `ver em Não é Assunto` link, the danger card
  `Excluir as tags com esses nomes` disabled until the impact preview, and the ledger below it; the
  verdict screen with the reciprocal `Grafias bloqueadas` button and the disclosure sentence naming
  where the tags are deleted; and `/assuntos/excecoes?termo=…` opening its ledger filtered
  (`1 de 6 termos vetados`) and scrolled to it, which is the landing the new link promises.
  `/assuntos/tags?aba=stopwords` was followed and answered `/assuntos/grafias`.
- **What was not verified.** The write path was exercised only to plant the fixture (`POST
  /subject-exclusions` for a synthetic term, which created the `EXCLUSION` ban the link is drawn
  from); the impact preview and the tag deletion were not run, and no tag was deleted. The mobile
  viewport was not rendered. The render database is scratch (`scrinalia_render`) and was migrated to
  `head` for the round; the synthetic term, its ban and the temporary account were left in it and
  belong to nobody's collection.
