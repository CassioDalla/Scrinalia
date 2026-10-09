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
