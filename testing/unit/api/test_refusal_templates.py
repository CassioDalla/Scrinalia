"""Every literal refusal template has its English counterpart, with the same placeholders.

The Portuguese template is the key (gettext-style): the call site keeps the sentence it always had,
and a missing translation falls back to it. This gate makes the fallback the exception a reviewer
sees, and pins the two sides to the same facts — a `{name}` on one side and not the other would be a
KeyError at request time.
"""

from __future__ import annotations

import ast
import pathlib
import re

from scrinalia.core.refusal_translations import TRANSLATIONS

SRC = pathlib.Path(__file__).resolve().parents[3] / "src" / "scrinalia"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _templates() -> set[str]:
    used: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "t"):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                used.add(node.args[0].value)
    return used


def test_every_refusal_template_is_translated() -> None:
    used = _templates()
    assert used, 'no `t("...")` call site is visible; the AST scan is broken.'
    missing = sorted(used - TRANSLATIONS.keys())
    assert not missing, "these refusal templates have no English sentence:\n  " + "\n  ".join(missing)


def test_the_two_sides_carry_the_same_facts() -> None:
    mismatched = {
        template: (sorted(PLACEHOLDER.findall(template)), sorted(PLACEHOLDER.findall(translated)))
        for template, translated in TRANSLATIONS.items()
        if sorted(PLACEHOLDER.findall(template)) != sorted(PLACEHOLDER.findall(translated))
    }
    assert not mismatched, f"a translation uses different placeholders than its template: {mismatched}"
