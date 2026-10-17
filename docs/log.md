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
