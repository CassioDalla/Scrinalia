"""Every route code a call site renders has an English sentence, and the helper respects the locale."""

from __future__ import annotations

import ast
import pathlib

from scrinalia.core.i18n import bind_locale, reset_locale
from scrinalia.domains.archive.schemas.responses import RouteMessageCode
from scrinalia.domains.archive.schemas.route_messages import ROUTE_MESSAGES_EN, route_message

SRC = pathlib.Path(__file__).resolve().parents[3] / "src" / "scrinalia"


def _codes_used() -> set[str]:
    used: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "route_message"):
                continue
            if not node.args:
                continue
            arg = node.args[0]
            if (
                isinstance(arg, ast.Attribute)
                and isinstance(arg.value, ast.Name)
                and arg.value.id == "RouteMessageCode"
            ):
                used.add(arg.attr)
    return used


def test_every_rendered_route_code_has_an_english_sentence() -> None:
    used = _codes_used()
    assert used, "no `route_message(RouteMessageCode.X, ...)` call site is visible; the scan is broken."
    missing = sorted(name for name in used if RouteMessageCode[name] not in ROUTE_MESSAGES_EN)
    assert not missing, f"these route codes render without an English sentence: {missing}"


def test_the_helper_answers_in_the_request_language_and_falls_back_to_portuguese() -> None:
    token = bind_locale("en-US")
    try:
        assert route_message(RouteMessageCode.SESSION_ENDED, "Sessão encerrada.") == "Signed out."
        assert (
            route_message(RouteMessageCode.USER_SESSIONS_REVOKED, "{ended} sessão(ões) encerrada(s).", ended=2)
            == "2 session(s) ended."
        )
    finally:
        reset_locale(token)

    assert route_message(RouteMessageCode.SESSION_ENDED, "Sessão encerrada.") == "Sessão encerrada."
