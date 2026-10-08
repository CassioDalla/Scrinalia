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
