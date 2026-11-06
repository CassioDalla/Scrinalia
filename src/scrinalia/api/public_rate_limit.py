"""A per-address brake on the public diffusion surface.

``/api/v1/public/*`` is the one surface designed to answer with no session, and it runs the same
search and facet queries as the curator's reads. The limit is a **process-local** sliding window,
like the sign-in brake, and the boundary is recorded in ADR 0025: the durable, global ceiling belongs
to the reverse proxy, while this one keeps a single process from being hammered by a client that
never signs in. ``uvicorn --workers N`` multiplies the effective ceiling by N, and the install guide
says so.

The refusal is produced **here** rather than by a guard, deliberately: a middleware answers before
routing, so a flood — including a path or a method that would end in 404/405 — costs no database
work. ``RequestContextMiddleware`` is outer, so the answer still carries ``X-Request-ID`` and reaches
the access line. The body has the shape every refusal uses (``error_code``/``message``), plus the
contract's ``code`` and a ``Retry-After``; it is not a ``DomainException`` because a middleware runs
outside Litestar's exception-handler layer, which is the same reason the authentication is a guard
and not a middleware.
"""

from __future__ import annotations

import json
import math

from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware
from litestar.status_codes import HTTP_429_TOO_MANY_REQUESTS
from litestar.types import ASGIApp, Receive, Scope, Send

from scrinalia.api.rate_limit import SlidingWindowLimiter
from scrinalia.core.config import get_settings
from scrinalia.core.i18n import refusal
from scrinalia.domains.archive.schemas.responses import RouteMessageCode

#: The surface this brake protects. It is the controller's own path, pinned to
#: ``PublicController.path`` by a test: a rename that left this constant behind would silently remove
#: the limit, and nothing else would fail.
PUBLIC_API_PREFIX = "/api/v1/public"

#: The identity of a refusal that is about the pace, not the request. ``error_code`` keeps the name
#: a client already branches on; ``code`` is the contract's ``RouteMessageCode``.
RATE_LIMITED_ERROR_CODE = "PublicRateLimited"

#: The process-wide window. It is shared by every request and by every app built in the process —
#: the same shape as ``provide_login_rate_limiter``'s cache — because a limiter per request would
#: count every hit in its own empty window and limit nothing.
_LIMITER = SlidingWindowLimiter()


def public_rate_limiter() -> SlidingWindowLimiter:
    """The process-wide window of the public surface."""
    return _LIMITER


def reset_public_rate_limiter() -> None:
    """Forgets every window. Used by the tests, and by nothing in production."""
    _LIMITER.reset()


def protects(path: str) -> bool:
    """Whether ``path`` belongs to the public surface, boundary-aware: ``/publicity`` does not."""
    return path == PUBLIC_API_PREFIX or path.startswith(f"{PUBLIC_API_PREFIX}/")


def client_address(scope: Scope) -> str:
    """
    The address the ASGI server reports, which is the proxy's when it rewrites ``X-Forwarded-For``
    and uvicorn is not told to trust it. The guide is where that distinction lives; this function
    only refuses to invent an address.
    """
    client = scope.get("client")
    return client[0] if client else "unknown"


class PublicRateLimitMiddleware(ASGIMiddleware):
    """Counts one hit per request under the public prefix and answers 429 when the window is full."""

    scopes = (ScopeType.HTTP,)

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        if not protects(str(scope.get("path") or "")):
            await next_app(scope, receive, send)
            return

        settings = get_settings()
        retry_after = _LIMITER.hit(
            client_address(scope),
            ceiling=settings.PUBLIC_RATE_LIMIT_MAX,
            window_seconds=settings.PUBLIC_RATE_LIMIT_WINDOW_SECONDS,
        )
        if retry_after is None:
            await next_app(scope, receive, send)
            return

        # The answer is built as ASGI messages instead of a ``Response``: this middleware runs
        # outside Litestar's handler layer, and a ``Response`` object is not an ASGI app. The body
        # keeps the shape every other refusal has, so the client's ``unwrap`` reads it unchanged.
        body = json.dumps(
            {
                "error_code": RATE_LIMITED_ERROR_CODE,
                "code": RouteMessageCode.PUBLIC_RATE_LIMITED.value,
                "message": refusal("public.rate_limited"),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": HTTP_429_TOO_MANY_REQUESTS,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    # Seconds, and at least 1: a header that says 0 invites an immediate retry
                    # that is still refused.
                    (b"retry-after", str(max(1, math.ceil(retry_after))).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
