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
