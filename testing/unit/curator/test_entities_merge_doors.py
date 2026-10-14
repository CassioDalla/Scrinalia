"""The entity merge has one panel and one write, and every door renders that panel (issue #87).

``/entidades/lista`` reaches the merge from three places: the selection on the Relevância tab, a pair
on the Similaridade tab, and the card that takes two names written by hand. Three entry points into
one write is the shape that drifts — a second merge form would promise numbers the planner did not
compute, and a door that built its own request could post an empty ``ids_to_merge``, which the
contract refuses with a 422 — so the doors are pinned to the same component and the write to a single
call site.

The parser is deliberately textual, like ``test_curator_copy.py`` and
``test_curator_search_state.py``: the SPA has no test runner of its own (there is no ``vitest``), and
the rules are about *source text* — one call to ``mergeEntities``, ``<MergePanel`` rendered by each
door and by nothing else, and a card that neither writes nor navigates.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CURATOR = REPO_ROOT / "apps" / "curator"
SRC = CURATOR / "src"
ROUTE = SRC / "routes" / "EntitiesRoute.tsx"

#: Every source file of the SPA, minus the generated client: a stale generated file is not a place
#: for this rule to live.
SOURCES = sorted(path for pattern in ("*.ts", "*.tsx") for path in SRC.rglob(pattern) if path.name != "schema.d.ts")

#: The doors, as the name of the top-level function that hands the panel its members. Relevância is
#: the screen itself, Similaridade is its own tab, and the card is the one issue #87 added.
DOORS = {"EntitiesRoute", "SimilarityTab", "MergeCard"}


def _blocks() -> dict[str, str]:
    """
    The route's top-level functions, by name.

    Split on the declaration itself — ``export`` included, because the screen's own component is
    exported and the tabs beside it are not — which is what turns "where is this call?" from a line
    number into a component.
    """
    blocks: dict[str, str] = {}
    body = ROUTE.read_text(encoding="utf-8")
    for chunk in re.split(r"\n(?:export )?function ", body)[1:]:
        name = re.split(r"[(<]", chunk, maxsplit=1)[0].strip()
        blocks[name] = chunk
    return blocks


def test_the_write_is_called_from_one_place_in_the_whole_front() -> None:
    """The panel owns the write; a second call site would be a second merge flow."""
    callers = [path.name for path in SOURCES if "mergeEntities({" in path.read_text(encoding="utf-8")]

    assert callers == ["EntitiesRoute.tsx"]

    owners = [name for name, block in _blocks().items() if "mergeEntities({" in block]
    assert owners == ["MergePanel"]


def test_every_door_renders_the_same_panel() -> None:
    """Three doors, one panel: the card is a third caller and never a second merge form."""
    owners = {name for name, block in _blocks().items() if "<MergePanel" in block}

    assert owners == DOORS


def test_the_card_hands_the_panel_its_members_and_nothing_else() -> None:
    """
    The card's whole job is to hand the panel two members.

    Calling the write itself, or putting its draft in the URL, are the two ways this door stops being
    the panel's third caller: the first would duplicate the confirmation step, the second would make a
    half-built list a view somebody else can be sent.
    """
    card = _blocks()["MergeCard"]

    assert "mergeEntities({" not in card
    assert "navigate(" not in card
    assert "previewEntityMerge(" not in card


def test_the_blocks_are_read_whole() -> None:
    """The scan itself, so a split that stopped working cannot pass the three rules above silently."""
    blocks = _blocks()

    assert DOORS
    assert DOORS.issubset(blocks)
    assert "previewEntityMerge(" in blocks["MergePanel"]
