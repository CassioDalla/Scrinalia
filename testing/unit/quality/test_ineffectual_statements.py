"""The local half of CodeQL's ``py/ineffectual-statement``: a stub body is ``pass``, never ``...``.

The ``security-and-quality`` pack flagged 137 statements in this repository, every one of them a bare
``...`` standing in for the body of a ``Protocol`` method, an ``@abstractmethod`` or an exception
class. ``...`` is legal Python and reads as intentional to a human, which is exactly why it survived
until a scanner looked: the statement evaluates a constant and drops it.

The replacement is not ``pass`` everywhere, and that is a measurement, not a preference: basedpyright
special-cases ``...`` as a stub body but rejects ``pass`` with ``reportReturnType`` — 95 errors
("must return a value on all code paths") on the stubs whose return type is not ``None``. So a method
body is ``raise NotImplementedError`` (terminal for the checker, a call for the scanner, and loud if
it ever runs) and a class body is ``pass``.

This test exists because a scanner reports only *after* the push: whoever writes
``def read(self, id: int) -> DTO: ...`` learns it from a red Security tab, not from their own run.
Fail locally instead of learning it there.

The scope is the one the other gates read — the type-check scope in ``pyrightconfig.json``
(``src/scrinalia``, ``main.py``, ``testing``, ``docs/_hooks``) plus ``migrations``, which CodeQL also
analyses. ``.dsh/skills/api/SKILL.md`` states the convention; this file is what makes it fail.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

#: What the gates read. ``migrations`` is in CodeQL's scan even though basedpyright excludes it, so a
#: revision file with a ``...`` body would alert with no local gate noticing.
SCANNED = ("src/scrinalia", "main.py", "testing", "docs/_hooks", "migrations")

#: A string literal that is the first statement of one of these is a docstring — the one constant
#: whose evaluation has a purpose, and the one this test must not flag.
_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _python_files() -> list[Path]:
    """Every first-party Python file inside :data:`SCANNED`, caches excluded."""
    files: list[Path] = []
    for entry in SCANNED:
        path = REPO_ROOT / entry
        files.extend([path] if path.is_file() else sorted(path.rglob("*.py")))
    return [path for path in files if "__pycache__" not in path.parts]


def _is_docstring(node: ast.Expr, parents: dict[int, ast.AST]) -> bool:
    """True for the string literal that documents a module, a class or a function."""
    parent = parents.get(id(node))
    if not isinstance(parent, _DOCSTRING_OWNERS):
        return False
    if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
        return False
    return bool(parent.body) and parent.body[0] is node


def ineffectual_statements(module: ast.Module) -> list[tuple[int, str]]:
    """
    The line and source of every statement that evaluates a constant or reads a name and drops it.

    Those two are the expression statements with no possible side effect, which is what the query
    calls ineffectual; a call, an ``await`` or a comprehension may act on the world and is left
    alone. A docstring is a constant too, and is the one the query accepts.
    """
    parents = {id(child): parent for parent in ast.walk(module) for child in ast.iter_child_nodes(parent)}
    found: list[tuple[int, str]] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, (ast.Constant, ast.Name)):
            continue
        if _is_docstring(node, parents):
            continue
        found.append((node.lineno, ast.unparse(node.value)))
    return sorted(found)


def test_the_check_notices_an_ellipsis_stub() -> None:
    """A gate that walks nothing passes silently, so the detector is pinned to what it forbids."""
    assert ineffectual_statements(ast.parse("def f() -> int: ...")) == [(1, "...")]
    assert ineffectual_statements(ast.parse("def f() -> int:\n    ...\n")) == [(2, "...")]
    assert ineffectual_statements(ast.parse("def f() -> None:\n    42\n    return None\n")) == [(2, "42")]
    assert ineffectual_statements(ast.parse("def f() -> None:\n    x\n")) == [(2, "x")]


def test_a_docstring_is_not_flagged() -> None:
    """The docstring is a constant with a purpose, in every position that may own one."""
    assert ineffectual_statements(ast.parse('"""Module."""\n')) == []
    assert ineffectual_statements(ast.parse('class C:\n    """Doc."""\n    x = 1\n')) == []
    assert ineffectual_statements(ast.parse('def f() -> None:\n    """Doc."""\n    pass\n')) == []


def test_no_statement_is_left_without_effect() -> None:
    """No ``...`` stub, and no constant or name left standing alone as a statement."""
    violations: list[str] = []
    for path in _python_files():
        for lineno, source in ineffectual_statements(ast.parse(path.read_text(encoding="utf-8"))):
            violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {source}")

    assert not violations, (
        "statement has no effect (CodeQL ``py/ineffectual-statement``) at "
        + ", ".join(violations)
        + " — give it a body that has an effect (``raise NotImplementedError`` for a stub method, "
        "``pass`` for a stub class) or delete the statement: an expression statement that evaluates a "
        "constant or reads a name is what the scanner reads as a stub written by accident."
    )
