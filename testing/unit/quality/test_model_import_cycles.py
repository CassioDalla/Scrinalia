"""No model package has a *runtime* import cycle — the scanner's premise, pinned locally.

CodeQL's ``py/unsafe-cyclic-import`` (the ``security-and-quality`` pack) reported seven findings in
``domains/archive/models/``: ``ArchiveDocument`` and its peers reference each other's types in
``Mapped[...]`` strings, so the modules form a cycle. They are dismissed as a **false positive**, and
this file is what keeps that dismissal honest — the cycle exists only for the type checker, because
every one of those imports sits inside ``if TYPE_CHECKING:`` and never executes.

That is a claim about the code, so it is measured rather than asserted. The guard is load-bearing:
removing one of the imports is 4 ``reportUndefinedVariable`` errors in basedpyright. And all four
modules import in any order in a fresh interpreter, because at runtime there is no cycle to hit.

CodeQL does not model the guard. ``is_import_time`` in its ``Cyclic.qll`` excludes only imports
lexically inside a ``def``, and an ``if`` block at module level is still import time for it.

So what is pinned here is the invariant the query is reaching for: **the sibling-import graph of a
model package, with the type-checker-only edges removed, is acyclic.** That is deliberately narrower
than "every sibling import is guarded", and the difference is measured: making *one* guarded import a
module-level one leaves the runtime graph acyclic — one edge is not a cycle.

Making both directions runtime is the crash the alert claims, and it is not hypothetical: measured on
a mutated tree, importing the models raises ``ImportError: cannot import name 'ArchiveDocument' from
partially initialized module``. It raises at pytest collection, before this test runs, because
``testing/conftest.py`` imports the application. The assertion below is what catches the cycle the
import order does not happen to reach, and it names the modules when it does.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOMAINS_ROOT = REPO_ROOT / "src" / "scrinalia" / "domains"


def _is_type_checking(node: ast.If) -> bool:
    """``if TYPE_CHECKING:`` or ``if typing.TYPE_CHECKING:``."""
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _is_type_checker_only(node: ast.stmt, parents: dict[int, ast.AST]) -> bool:
    """True when the statement sits inside an ``if TYPE_CHECKING:`` block."""
    current: ast.AST = node
    while id(current) in parents:
        parent = parents[id(current)]
        if isinstance(parent, ast.If) and _is_type_checking(parent):
            return True
        current = parent
    return False


def runtime_sibling_imports(tree: ast.Module, siblings: set[str], prefix: str) -> set[str]:
    """
    The siblings ``tree`` imports **at runtime**, as module stems.

    ``siblings`` are the module stems of the package and ``prefix`` its dotted path
    (``scrinalia.domains.archive.models``). An import inside ``if TYPE_CHECKING:`` is left out on
    purpose: that is exactly the difference between the type-checker cycle and a runtime one.

    ``from . import document`` counts twice, and both edges are real: it binds the module and it runs
    the package's ``__init__``, which imports every sibling.
    """
    parents = {id(child): parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)) or _is_type_checker_only(node, parents):
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(prefix + "."):
                    found.add(alias.name[len(prefix) + 1 :].split(".")[0])
            continue

        module = node.module or ""
        if node.level == 1:
            if module:
                found.update({module} & siblings)
            else:
                found.update({alias.name for alias in node.names} & siblings)
                found.add("__init__")
        elif module.startswith(prefix + "."):
            found.add(module[len(prefix) + 1 :].split(".")[0])
    return found


def find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """A cycle in ``graph`` as the path that closes it, or ``None`` when the graph is acyclic."""
    visited: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()

    def visit(node: str) -> list[str] | None:
        visited.add(node)
        stack.append(node)
        on_stack.add(node)
        for neighbour in sorted(graph.get(node, set())):
            if neighbour not in graph:
                continue
            if neighbour in on_stack:
                return [*stack[stack.index(neighbour) :], neighbour]
            if neighbour not in visited and (found := visit(neighbour)):
                return found
        stack.pop()
        on_stack.discard(node)
        return None

    for node in sorted(graph):
        if node not in visited and (found := visit(node)):
            return found
    return None


def test_the_detector_ignores_a_guarded_import_and_keeps_a_runtime_one() -> None:
    """A gate that sees no edges passes silently, so the two readings are pinned apart."""
    siblings = {"document", "entity"}
    prefix = "scrinalia.domains.archive.models"

    guarded = ast.parse(
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from .entity import ArchiveEntity\n"
    )
    runtime = ast.parse("from .entity import ArchiveEntity\n")
    package = ast.parse("from . import entity\n")
    absolute = ast.parse(f"import {prefix}.entity\n")

    assert runtime_sibling_imports(guarded, siblings, prefix) == set()
    assert runtime_sibling_imports(runtime, siblings, prefix) == {"entity"}
    assert runtime_sibling_imports(package, siblings, prefix) == {"entity", "__init__"}
    assert runtime_sibling_imports(absolute, siblings, prefix) == {"entity"}


def test_the_cycle_detector_notices_a_cycle() -> None:
    """The other half of the same problem: a detector that never finds a cycle is no gate either."""
    assert find_cycle({"document": {"entity"}, "entity": set()}) is None
    assert find_cycle({"__init__": {"document"}, "document": {"enums"}, "enums": set()}) is None
    cycle = find_cycle({"document": {"entity"}, "entity": {"document"}})
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"document", "entity"}


def test_no_model_package_has_a_runtime_import_cycle() -> None:
    """Every ``domains/*/models`` package imports its siblings only in one direction at runtime."""
    offenders: list[str] = []
    for package in sorted(DOMAINS_ROOT.glob("*/models")):
        prefix = f"scrinalia.domains.{package.parent.name}.models"
        stems = {path.stem for path in package.glob("*.py")}
        graph = {
            path.stem: runtime_sibling_imports(ast.parse(path.read_text(encoding="utf-8")), stems, prefix)
            for path in sorted(package.glob("*.py"))
        }
        cycle = find_cycle(graph)
        if cycle is not None:
            relative = package.relative_to(REPO_ROOT)
            offenders.append(f"{relative}: {' -> '.join(cycle)}")

    assert not offenders, (
        "a model package gained a runtime import cycle: "
        + "; ".join(offenders)
        + " — the modules reference each other's types in ``Mapped[...]`` strings, so the import "
        "belongs inside ``if TYPE_CHECKING:`` and never at module level. This is the premise of "
        "CodeQL's ``py/unsafe-cyclic-import``, whose seven findings on the archive models are "
        "dismissed as a false positive; a real cycle is the crash it was pointing at."
    )
