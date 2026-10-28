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

from scrinalia.core.i18n import bind_locale, reset_locale


class LocaleMiddleware(ASGIMiddleware):
    """Binds the request's language for the sentence helpers and the refusal handler."""

    scopes = (ScopeType.HTTP,)

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        token = bind_locale(Headers.from_scope(scope).get("accept-language"))
        try:
            await next_app(scope, receive, send)
        finally:
            reset_locale(token)
