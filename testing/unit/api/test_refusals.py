"""Every refusal code the code raises exists in the catalogue, in both languages.

The catalogue is the one place a refusal's sentence is defined. A code with no entry is a KeyError at
request time — the loud failure — but only if the code is reachable; this gate makes the mistake a
failing test instead of an incident.
"""

from __future__ import annotations

import ast
import pathlib

from scrinalia.core.i18n import REFUSALS
from scrinalia.core.locale import Locale

SRC = pathlib.Path(__file__).resolve().parents[3] / "src" / "scrinalia"


def _codes_used() -> set[str]:
    used: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "refusal"):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                used.add(node.args[0].value)
    return used


def test_every_refusal_in_the_source_has_a_sentence() -> None:
    used = _codes_used()
    assert used, "no `refusal(...)` call site is visible to the gate; the AST scan is broken."
    missing = sorted(used - REFUSALS.keys())
    assert not missing, f"these refusal codes have no catalogue entry: {missing}"


def test_both_languages_are_present_and_well_formed() -> None:
    empty = sorted(code for code, texts in REFUSALS.items() if not all(text.strip() for text in texts.values()))
    assert not empty, f"these refusal codes have an empty sentence: {empty}"
    for code, texts in REFUSALS.items():
        assert set(texts) == {Locale.PT_BR, Locale.EN}, f"{code} is not translated to both locales."
