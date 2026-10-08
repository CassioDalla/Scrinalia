"""The documentation coverage gate (ADR 0010).

The documentation twin of ``testing/unit/api/test_route_access.py``: that test fails when an
operation ships without a declared permission, this one fails when a documented surface ships
without a page that mentions it. The failure lists what is missing, so adding the line is the
whole fix — and removing an item from a page to make the test pass is a visible decision in a
diff instead of a silent omission.

Coverage is decided against the **committed contract** and the real catalogues, never against a
running application: the worker catalogue is cheap on purpose (it imports no worker) and the
contract is a committed file.
"""

from __future__ import annotations

import json
import re
from importlib import import_module
from pathlib import Path

from scrinalia.core.base import Base
from scrinalia.core.config import Settings
from scrinalia.domains.archive.workers.catalogue import WORKER_CATALOGUE

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "docs"
CONTRACT = REPO_ROOT / "packages" / "api-contract" / "openapi.json"

#: The page that owns each documented surface. One page per surface on purpose: "which page do
#: I edit when a worker lands" has exactly one answer.
GUIDES = {
    "workers": "guides/operate.md",
    "settings": "guides/install.md",
    "screens": "guides/curate.md",
    "tables": "guides/data-model.md",
    "adrs": "adr/index.md",
}

_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")
_ROUTE_PATH = re.compile(r'path:\s*"([^"]+)"')


def text(rel: str) -> str:
    """The whole text of a documentation page, or an empty string when it does not exist."""
    path = DOCS / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


def docs_text() -> str:
    """Every page of the site, concatenated."""
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(DOCS.rglob("*.md")))


def _missing(items: list[str], page: str) -> list[str]:
    """The items a page does not mention."""
    body = text(page)
    return [item for item in items if item not in body]


def test_the_four_guides_exist() -> None:
    absent = [page for page in GUIDES.values() if not (DOCS / page).exists()]
    assert not absent, f"the documentation base is missing: {absent}"


def test_every_worker_is_in_the_operations_guide() -> None:
    missing = _missing(list(WORKER_CATALOGUE), GUIDES["workers"])
    assert not missing, (
        f"{GUIDES['workers']} does not mention these workers of "
        f"`workers/catalogue.py`: {missing}. A new worker means a spec there and a paragraph here."
    )


def test_every_setting_is_in_the_install_guide() -> None:
    missing = _missing(list(Settings.model_fields), GUIDES["settings"])
    assert not missing, (
        f"{GUIDES['settings']} does not document these settings of `core/config.py`: {missing}. "
        "Every field belongs in the variable table."
    )


def test_every_screen_is_in_the_curation_guide() -> None:
    router = (REPO_ROOT / "apps" / "curator" / "src" / "router.tsx").read_text(encoding="utf-8")
    body = text(GUIDES["screens"])
    missing = [path for path in _ROUTE_PATH.findall(router) if not _mentions_route(body, path)]
    assert not missing, (
        f"{GUIDES['screens']} does not mention these screens of `apps/curator/src/router.tsx`: "
        f"{missing}. Every screen is a decision the archivist takes there."
    )


def _mentions_route(body: str, path: str) -> bool:
    """Whether a page names a route, tolerating how a dynamic segment is written.

    ``/acervo/$descriptionId`` is the router's spelling; a page may write
    ``/acervo/{descriptionId}`` or ``/acervo/:descriptionId``, and all three are the same screen.
    """
    forms = {path, re.sub(r"\$\w+", "{id}", path), re.sub(r"\$\w+", ":id", path)}
    return any(form in body for form in forms)


def _load_models() -> None:
    """Import every model module, the set ``testing/conftest.py`` imports before ``create_all``.

    ``staging`` belongs here. Forgetting it hides the only table of a pipeline layer
    (``staging_documents``) from the gate, which is exactly the kind of omission the gate exists
    to catch. Measured: 33 tables without it, 34 with.
    """
    for module in (
        "scrinalia.domains.archive.models",
        "scrinalia.domains.identity.models",
        "scrinalia.domains.ingestion.models",
        "scrinalia.domains.staging.models",
    ):
        import_module(module)


def test_every_table_is_in_the_data_model_guide() -> None:
    _load_models()
    missing = _missing(sorted(Base.metadata.tables), GUIDES["tables"])
    assert not missing, (
        f"{GUIDES['tables']} does not document these tables: {missing}. "
        "The page is the map of the schema; a new table means a line here."
    )


def test_every_adr_is_linked_from_the_index() -> None:
    index = text(GUIDES["adrs"])
    missing = [
        path.name for path in sorted((DOCS / "adr").glob("*.md")) if path.name != "index.md" and path.name not in index
    ]
    assert not missing, (
        f"`{GUIDES['adrs']}` does not link these decisions: {missing}. "
        "An ADR nobody can reach is a decision nobody reads."
    )


def test_every_api_resource_is_mentioned_somewhere() -> None:
    """A whole new resource cannot land without a page using its name.

    Deliberately weaker than the per-item checks: the guides do not enumerate the 111
    operations (the committed contract is that reference), but a new first segment under
    ``/api/v1`` is a new surface, and no page naming it at all is the silent case this catches.
    """
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    groups = {
        segments[0]
        for path in document.get("paths", {})
        if (segments := [part for part in path.split("/") if part][2:])
    }
    body = docs_text()
    missing = sorted(group for group in groups if group not in body)
    assert not missing, f"no page mentions the API resource(s): {missing}"
