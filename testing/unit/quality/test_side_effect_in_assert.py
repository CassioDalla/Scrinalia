"""The local half of CodeQL's ``py/side-effect-in-assert``: the assert asserts, it does not act.

Everything inside an ``assert`` disappears under ``python -O`` — the assertion *and* whatever it
calls. When the call is the point (an HTTP request, a subprocess), the optimized run silently stops
exercising it and the test passes for the wrong reason.

The query (``python/ql/src/Statements/SideEffectInAssert.ql``) is a **name** heuristic rather than a
semantic one. It flags a call inside an assert whose function is named ``print``, ``write``,
``append``, ``pop``, ``remove``, ``discard``, ``delete``, ``close``, ``open`` or ``exit``; a call into
``subprocess.call``/``check_call``/``check_output``; and a ``yield`` (outside a comprehension). That is
why the nine findings in this repository were all the same shape — an HTTP ``DELETE`` through a test
client, whose method is named ``delete``: ``assert client.delete(url).status_code == 405``. Two
readings of that heuristic are pinned below so the detector cannot drift from it in either direction:
``response.json()`` is a call but *not* reported, and ``queue.pop()`` is.

The remedy is the one the query recommends: bind the call to a variable, then assert on the variable.
The suite runs with asserts enabled, so the two forms are equivalent there — but only one of them
survives ``-O`` with its request intact.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The scope the gates read — the same one ``test_ineffectual_statements.py`` uses (the type-check
#: scope plus ``migrations``, which CodeQL also analyses).
SCANNED = ("src/scrinalia", "main.py", "testing", "docs/_hooks", "migrations")

#: ``func_with_side_effects`` in the query, name for name.
_SIDE_EFFECTING_NAMES = frozenset(
    {"print", "write", "append", "pop", "remove", "discard", "delete", "close", "open", "exit"}
)

#: ``call_with_side_effect`` in the query: the ``subprocess`` module's blocking calls.
_SUBPROCESS_CALLS = frozenset({"call", "check_call", "check_output"})

_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _python_files() -> list[Path]:
    """Every first-party Python file inside :data:`SCANNED`, caches excluded."""
    files: list[Path] = []
    for entry in SCANNED:
        path = REPO_ROOT / entry
        files.extend([path] if path.is_file() else sorted(path.rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts]


def _called_name(node: ast.Call) -> str | None:
    """The name the query matches on: an attribute's name, or a bare function name."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _is_subprocess_call(node: ast.Call) -> bool:
    """``subprocess.call(...)`` and siblings, whichever way ``subprocess`` was imported as."""
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in _SUBPROCESS_CALLS:
        return False
    owner = node.func.value
    if isinstance(owner, ast.Name):
        return owner.id == "subprocess"
    return isinstance(owner, ast.Attribute) and owner.attr == "subprocess"


def _inside_comprehension(node: ast.AST, parents: dict[int, ast.AST]) -> bool:
    """A ``yield`` inside a comprehension is the comprehension's, not the assert's."""
    current: ast.AST = node
    while id(current) in parents:
        current = parents[id(current)]
        if isinstance(current, _COMPREHENSIONS):
            return True
    return False


def side_effects_in_asserts(tree: ast.Module) -> list[tuple[int, str]]:
    """The line and name of every side-effecting expression found inside an ``assert``."""
    parents = {id(child): parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    found: list[tuple[int, str]] = []
    for assert_node in ast.walk(tree):
        if not isinstance(assert_node, ast.Assert):
            continue
        for node in ast.walk(assert_node.test):
            if isinstance(node, ast.Call):
                name = _called_name(node)
                if name in _SIDE_EFFECTING_NAMES:
                    found.append((assert_node.lineno, name))
                elif _is_subprocess_call(node):
                    found.append((assert_node.lineno, f"subprocess.{name}"))
            elif isinstance(node, (ast.Yield, ast.YieldFrom)) and not _inside_comprehension(node, parents):
                found.append((assert_node.lineno, "yield"))
    return sorted(found)


def test_the_check_separates_a_side_effect_from_a_plain_call() -> None:
    """Both readings are pinned, because a detector that reports nothing passes silently."""
    assert side_effects_in_asserts(ast.parse('assert client.delete("/x").status_code == 405\n')) == [(1, "delete")]
    assert side_effects_in_asserts(ast.parse("assert queue.pop() == 1\n")) == [(1, "pop")]
    assert side_effects_in_asserts(ast.parse("assert subprocess.call(['ls']) == 0\n")) == [(1, "subprocess.call")]
    assert side_effects_in_asserts(ast.parse("def g():\n    assert (yield 1)\n")) == [(2, "yield")]

    assert (
        side_effects_in_asserts(ast.parse('response = client.delete("/x")\nassert response.status_code == 405\n')) == []
    )
    assert side_effects_in_asserts(ast.parse('assert response.json()["total"] == 0\n')) == []
    assert side_effects_in_asserts(ast.parse("assert [y for y in range(3)] == [0, 1, 2]\n")) == []


def test_no_assert_has_a_side_effect() -> None:
    """No call the query names, and no ``yield``, may sit inside an assert."""
    violations: list[str] = []
    for path in _python_files():
        for lineno, name in side_effects_in_asserts(ast.parse(path.read_text(encoding="utf-8"))):
            violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {name}()")

    assert not violations, (
        "an assert does the work instead of asserting it (CodeQL ``py/side-effect-in-assert``) at "
        + ", ".join(violations)
        + " — bind the call and assert on the result (``response = client.delete(url)`` then "
        "``assert response.status_code == 405``): under ``python -O`` the assert and its call both "
        "disappear, and the test stops exercising what it was written to protect."
    )
