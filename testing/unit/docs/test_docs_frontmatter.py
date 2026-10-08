"""The front-matter contract of ADR 0010, pinned as an exact partition.

A page that documents a surface declares where that surface lives (``sources:``) and a
translation declares what it translates (``translation_of:``). A new page is a deliberate
addition to both sets, the way a new field is a deliberate addition to ``NOT_PUBLIC_FIELDS``:
the default is "not tracked", and this test is what turns the decision into a line in a diff.

The parser is **imported from the shipped hook** rather than reimplemented here. That is the
same rule the hierarchy diagnostic follows: a second copy of the rule keeps passing while the
shipped one drifts.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "docs"
HOOK_PATH = DOCS / "_hooks" / "freshness.py"

#: Pages that document a surface, and therefore declare the code they document.
SOURCED_PAGES = (
    "guides/install.md",
    "guides/operate.md",
    "guides/curate.md",
    "guides/data-model.md",
)

#: Pages that carry a Portuguese translation. The index is translated; the ADRs are not
#: (ADR 0010) and neither is the ledger.
TRANSLATED_PAGES = ("index.md", *SOURCED_PAGES)

#: The only keys a page may declare. ``reviewed`` and a stored revision were rejected on
#: purpose: the marker is derived from git, so a page cannot lie about having been read.
ALLOWED_KEYS = {"sources", "translation_of"}


def _load_hook() -> Any:
    spec = importlib.util.spec_from_file_location("docs_freshness_hook", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The module must be in ``sys.modules`` before it executes: ``@dataclass`` resolves its
    # annotations through ``sys.modules[cls.__module__]``, which is ``None`` otherwise.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HOOK = _load_hook()


def meta(rel: str) -> dict[str, Any]:
    """The front matter a page declares, read by the shipped parser."""
    path = DOCS / rel
    assert path.exists(), f"`{rel}` does not exist; the documentation base is incomplete"
    return HOOK.parse_front_matter(path.read_text(encoding="utf-8"))


def translated() -> list[str]:
    return sorted(path.relative_to(DOCS).as_posix() for path in DOCS.rglob("*.pt.md"))


def test_the_shipped_parser_reads_the_declared_shape() -> None:
    sample = (
        "---\n"
        "sources:\n"
        "  - src/scrinalia/core/config.py\n"
        "  - src/scrinalia/domains/archive/workers/**\n"
        "---\n"
        "\n# A page\n"
    )
    assert HOOK.parse_front_matter(sample) == {
        "sources": [
            "src/scrinalia/core/config.py",
            "src/scrinalia/domains/archive/workers/**",
        ]
    }
    assert HOOK.parse_front_matter("# No front matter\n") == {}
    assert HOOK.parse_front_matter("---\ntranslation_of: index.md\n---\n") == {"translation_of": "index.md"}


def test_sourced_pages_declare_their_sources() -> None:
    for rel in SOURCED_PAGES:
        declared = meta(rel).get("sources")
        assert isinstance(declared, list) and declared, (
            f"`{rel}` declares no `sources:`; without it the freshness report can never decide "
            "whether the page is stale"
        )
        assert all(isinstance(source, str) and source for source in declared)


def test_the_translated_set_is_exactly_the_declared_one() -> None:
    assert translated() == sorted(f"{rel[:-3]}.pt.md" for rel in TRANSLATED_PAGES), (
        "the set of Portuguese pages changed. Adding a translation is a deliberate decision: "
        "add the page to TRANSLATED_PAGES in the same change"
    )


def test_every_translation_declares_what_it_translates() -> None:
    for rel in TRANSLATED_PAGES:
        page = f"{rel[:-3]}.pt.md"
        declared = meta(page).get("translation_of")
        assert declared == rel, f"`{page}` must declare `translation_of: {rel}`, not {declared!r}"
        assert (DOCS / rel).exists(), f"`{page}` translates `{rel}`, which does not exist"


def test_no_page_declares_a_key_outside_the_contract() -> None:
    for rel in (*SOURCED_PAGES, *(f"{page[:-3]}.pt.md" for page in TRANSLATED_PAGES)):
        keys = set(meta(rel))
        assert keys <= ALLOWED_KEYS, (
            f"`{rel}` declares {sorted(keys - ALLOWED_KEYS)}. The contract is "
            f"{sorted(ALLOWED_KEYS)}: the revision is derived from git, never stored"
        )
        assert len(keys) == 1, f"`{rel}` must declare exactly one key, got {sorted(keys)}"


def test_every_declared_source_matches_a_file() -> None:
    for rel in SOURCED_PAGES:
        for source in meta(rel)["sources"]:
            matches = list(REPO_ROOT.glob(source))
            assert matches, (
                f"`{rel}` declares `{source}`, which matches nothing. A source that matches no "
                "file makes the page permanently fresh"
            )


def _heading_levels(rel: str) -> list[int]:
    """The level of every heading, ignoring the fenced code blocks a ``#`` may appear in."""
    lines = (DOCS / rel).read_text(encoding="utf-8").splitlines()
    levels: list[int] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and (match := re.match(r"^(#{1,6})\s", line)):
            levels.append(len(match.group(1)))
    return levels


def test_a_translation_keeps_the_heading_structure_of_its_page() -> None:
    """Portuguese is a translation, not a second text: it may not add or drop a section."""
    for rel in TRANSLATED_PAGES:
        page = f"{rel[:-3]}.pt.md"
        assert _heading_levels(page) == _heading_levels(rel), (
            f"`{page}` does not mirror the section structure of `{rel}`. A translation carries the "
            "same sections; a new fact belongs in the English page first"
        )


def test_the_ledger_has_a_range_the_hook_can_read() -> None:
    floor = HOOK.ledger_floor(DOCS)
    assert floor, (
        "`docs/log.md` has no parseable `- **Range:** `start..end`` line; without it every "
        "triaged page is reported stale again on the next build"
    )
