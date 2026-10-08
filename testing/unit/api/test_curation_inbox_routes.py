"""The inbox promises a card and a place to go; the place has to exist.

The queue catalogue lives in the API and the set of screens the shell can open lives in the SPA, so
neither side can see the other. The invariant is checked here, reading the TSX the same way the
documentation coverage test reads the router.

It is worth a test because the failure is silent and looks like a product decision: a card whose
route the shell does not list renders "tela pendente" for a screen that is finished, which is how
``/entidades/conflitos`` and ``/qualidade/anomalias`` stayed hidden after being built.
"""

from __future__ import annotations

import re
from pathlib import Path

from scrinalia.domains.archive.services.curation_service import QUEUE_CATALOGUE

REPO_ROOT = Path(__file__).resolve().parents[3]
INBOX = REPO_ROOT / "apps" / "curator" / "src" / "routes" / "InboxRoute.tsx"
ROUTER = REPO_ROOT / "apps" / "curator" / "src" / "router.tsx"

_BLOCK = re.compile(r"const IMPLEMENTED = new Set\(\[(.*?)\]\)", re.DOTALL)
_STRING = re.compile(r'"([^"]+)"')
_ROUTE_PATH = re.compile(r'path:\s*"([^"]+)"')


def _implemented() -> set[str]:
    block = _BLOCK.search(INBOX.read_text(encoding="utf-8"))
    assert block is not None, "`IMPLEMENTED` is no longer a `new Set([...])` literal in InboxRoute.tsx"
    return set(_STRING.findall(block.group(1)))


def _router_paths() -> set[str]:
    return set(_ROUTE_PATH.findall(ROUTER.read_text(encoding="utf-8")))


def _path_of(route: str) -> str:
    """The route without its query string, exactly like ``pathOf`` in InboxRoute.tsx.

    A queue may point at a filtered list (``/acervo/lista?status=PENDING_AI``): the query is the
    filter, the path is the screen, and the shell decides on the path.
    """
    return route.split("?", 1)[0]


def test_every_queue_card_points_at_a_screen_the_shell_can_open() -> None:
    openable = _implemented()
    missing = sorted({_path_of(route) for _, _, route, _ in QUEUE_CATALOGUE if _path_of(route) not in openable})
    assert not missing, (
        f"the inbox renders these queues as 'tela pendente' although the screens exist: {missing}. "
        "Add the route to `IMPLEMENTED` in InboxRoute.tsx"
    )


def test_every_openable_route_is_a_real_screen() -> None:
    """The other direction: a route the shell claims to open has to exist in the router."""
    paths = _router_paths()
    unknown = sorted(route for route in _implemented() if route not in paths)
    assert not unknown, f"`IMPLEMENTED` lists routes no screen declares: {unknown}"
