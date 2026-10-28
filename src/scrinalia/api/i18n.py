"""The request's language, and the sentences the API composes in it (ADR 0020 §4).

The header is the only channel: a screen sends ``Accept-Language`` with every request, and the
response — a confirmation or a refusal — is written in the language the person is reading. The
locale rides in a ``ContextVar`` because the sentences are composed in services and guards as well
as in controllers, and threading a ``Request`` through those layers would make the domain know HTTP.
"""

from __future__ import annotations

from litestar.datastructures import Headers
from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from scrinalia.core.i18n import bind_locale, current_locale, reset_locale
from scrinalia.core.locale import Locale
from scrinalia.domains.archive.schemas.responses import RouteMessageCode


class LocaleMiddleware(ASGIMiddleware):
    """Binds the request's language for the sentence helpers and the refusal handler."""

    scopes = (ScopeType.HTTP,)

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        token = bind_locale(Headers.from_scope(scope).get("accept-language"))
        try:
            await next_app(scope, receive, send)
        finally:
            reset_locale(token)


#: The sentences a route answers, in the two languages. Additive by nature: a code without an entry
#: is a code whose call site cannot call ``route_message`` yet.
ROUTE_MESSAGES: dict[RouteMessageCode, dict[Locale, str]] = {
    RouteMessageCode.SESSION_ENDED: {
        Locale.PT_BR: "Sessão encerrada.",
        Locale.EN: "Signed out.",
    },
    RouteMessageCode.PASSWORD_CHANGED: {
        Locale.PT_BR: "Senha alterada. As outras sessões desta conta foram encerradas.",
        Locale.EN: "Password changed. The account's other sessions were ended.",
    },
}


def route_message(code: RouteMessageCode, **facts: object) -> str:
    """
    The sentence for a route answer, in the request's language.

    A fact is interpolated from the template; a code with no entry fails loudly, because the call
    site that asks for one is the call site whose translation was forgotten.
    """
    entry = ROUTE_MESSAGES.get(code)
    if entry is None:
        raise KeyError(f"no route message for {code}")
    return entry[current_locale()].format(**facts)
