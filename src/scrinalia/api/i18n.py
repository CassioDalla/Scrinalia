"""The request's language, and the sentences the API composes in it (ADR 0020 §4).

The header is the only channel: a screen sends ``Accept-Language`` with every request, and the
response — a confirmation or a refusal — is written in the language the person is reading. The
locale rides in a ``ContextVar`` because the sentences are composed in services and guards as well
as in controllers, and threading a ``Request`` through those layers would make the domain know HTTP.
"""

from __future__ import annotations

from contextvars import ContextVar

from litestar.datastructures import Headers
from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from scrinalia.core.locale import DEFAULT_LOCALE, Locale
from scrinalia.domains.archive.schemas.responses import RouteMessageCode

_current: ContextVar[Locale] = ContextVar("scrinalia_locale", default=DEFAULT_LOCALE)


def negotiate_locale(header: str | None) -> Locale:
    """
    The best supported language of an ``Accept-Language`` header.

    The header is a list of tags with optional ``q`` weights; the highest one this API speaks wins,
    and anything else falls back to ``pt-BR`` — the product's language, which is also what a client
    that sends no header has always received. ``q=0`` means "not acceptable" and is skipped.
    """
    if not header:
        return DEFAULT_LOCALE

    candidates: list[tuple[float, str]] = []
    for part in header.split(","):
        tag, _, params = part.strip().partition(";")
        tag = tag.strip().lower()
        if not tag:
            continue
        quality = 1.0
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if quality > 0:
            candidates.append((quality, tag))

    for _, tag in sorted(candidates, key=lambda item: item[0], reverse=True):
        if tag.startswith("pt"):
            return Locale.PT_BR
        if tag.startswith("en"):
            return Locale.EN
    return DEFAULT_LOCALE


def current_locale() -> Locale:
    """The language of the request being served."""
    return _current.get()


class LocaleMiddleware(ASGIMiddleware):
    """Binds the request's language for the sentence helpers and the refusal handler."""

    scopes = (ScopeType.HTTP,)

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        header = Headers.from_scope(scope).get("accept-language")
        token = _current.set(negotiate_locale(header))
        try:
            await next_app(scope, receive, send)
        finally:
            _current.reset(token)


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
