"""The curator SPA's search-state contract.

A screen keeps its filters and its page in the URL, so the back button and a shared link work. One
helper per screen folds the **changes** it is handed — a filter, a page, or both — into the search the
route already has:

    navigate({ to: "/acervo/lista", search: { ...search, ...changes, offset: changes.offset } })

The defect this gate exists for is a fold that decides the page **after** the changes it was handed:

    search: { ...search, ...changes, offset: 0 }

The literal sits after the spread, so it overwrites the page the caller just set. It shipped on
`/acervo/lista` (issue #66): "Próxima" built `{ …, offset: 25, offset: 0 }` and reloaded page 1
forever, while a hand-typed `?offset=25` worked — the URL carried the page and the request read it, so
the defect was invisible to every gate and to a reviewer. `tsc`, ESLint and the Vite build are green on
both spellings, and the same literal serves two intents: a filter change *should* return to the first
page, which is why `offset: 0` looked right in four screens, and only the call sites that pass a page
were broken.

The rule: an object literal that spreads `changes` takes `offset` from `changes.offset`. A caller that
wants the first page sends no page at all. `/assuntos/tags` already had this shape one commit before the
same defect survived on `/acervo/lista`, which is the argument for a gate instead of a fifth repair.

The parser is deliberately textual, like `test_curator_copy.py`: the SPA has no test runner of its own
(there is no `vitest`), and this rule is about source text.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CURATOR = REPO_ROOT / "apps" / "curator"
SRC = CURATOR / "src"

#: Every source file of the SPA. `schema.d.ts` is generated, and a stale generated file is not a
#: place for this rule to live.
SOURCES = sorted(path for pattern in ("*.ts", "*.tsx") for path in SRC.rglob(pattern) if path.name != "schema.d.ts")

#: A search object that spreads `changes` and then decides `offset` with anything but the change.
#: ``\s`` spans the newlines a formatter may put between the two keys, and the negative lookahead —
#: which has to swallow the space after the colon itself, or the space defeats it — is what makes the
#: good shape, ``offset: changes.offset``, pass.
FORCED_OFFSET = re.compile(r"\.\.\.changes\s*,\s*offset:\s*(?!\s*changes\.offset)")


def offenders() -> list[str]:
    """Every place a literal page is written after the changes, as ``file:line``."""
    found: list[str] = []
    for path in SOURCES:
        body = path.read_text(encoding="utf-8")
        for match in FORCED_OFFSET.finditer(body):
            line = body.count("\n", 0, match.start()) + 1
            found.append(f"{path.relative_to(CURATOR).as_posix()}:{line}")
    return found


def test_the_page_a_caller_hands_over_is_not_swallowed() -> None:
    """``offset`` written after ``...changes`` comes from ``changes``, so a page button keeps its page."""
    found = offenders()
    assert not found, (
        f"these search objects decide `offset` after spreading `changes`: {found}. The literal "
        'overwrites the page the caller just set, so "Próxima" reloads page 1 forever (issue #66). '
        "Write `offset: changes.offset`: a filter change returns to the first page because it sends no "
        "page, and a page a caller does send survives."
    )


def test_the_pattern_sees_a_forced_page_and_not_the_good_shape() -> None:
    """The scan itself, on synthetic input: a pattern that matches nothing would pass forever.

    Synthetic on purpose, like the sanity checks of `test_curator_copy.py` — the behaviour under test
    is the pattern, not the state of the screens on the day it was written.
    """
    assert FORCED_OFFSET.search("search: { ...search, ...changes, offset: 0 }")
    assert FORCED_OFFSET.search("search: { ...search, ...changes, offset: undefined }")
    assert FORCED_OFFSET.search("search: {\n  ...search,\n  ...changes,\n  offset: 0,\n}"), (
        "the pattern stopped reading an object the formatter wrapped across lines."
    )
    assert not FORCED_OFFSET.search("search: { ...search, ...changes, offset: changes.offset }")
    assert not FORCED_OFFSET.search("search: { ...search, ...changes }")
