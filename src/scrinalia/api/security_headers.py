"""The response-header policy, applied once, for every route the application serves.

The application and the reverse proxy have two different jobs (ADR 0025). The proxy terminates TLS
and, if the deployment needs a global or durable limit, enforces it there. The application owns the
headers and the per-process brake, because it is the one origin that serves both the SPA and the
JSON, and because only it can be tested against the bundle that Vite emits. The install guide tells
the operator what the proxy must **not** duplicate.

The policy is one header set for HTML and JSON alike. A CSP on JSON is inert, but it means there is
no second path to keep in step: everything that is not a documentation page is covered by the same
line, and the test that asks for a JSON answer and the test that asks for an HTML answer read the
same constants.

The one documented exception is ``/schema``. Litestar serves Swagger, Redoc, RapiDoc and Stoplight
there, and each render plugin loads its scripts and styles from a CDN and then runs an inline
initialiser; a strict CSP would blank every one of them. The exception is per prefix and explicit,
not a hole in the policy.
"""

from __future__ import annotations

from litestar.datastructures import MutableScopeHeaders
from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from scrinalia.core.config import get_settings

#: The policy, in one place. ``script-src 'self'`` is the whole script allowance: the built SPA entry
#: is a ``<script type="module" crossorigin src="/assets/...">`` and there is no inline script.
#: ``style-src`` still needs ``'unsafe-inline'`` because six screens compute a dynamic
#: ``style={{...}}`` (the tree indentation), and an attribute style cannot carry a nonce. ``img-src``
#: allows ``data:`` for a future inline placeholder; thumbnails are same-origin. ``font-src`` names
#: the one font the build carries: PT Serif is bundled under ``/assets/fonts/`` and served from this
#: origin, so naming the origin keeps a future external font a deliberate change.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-src 'none'",
        "frame-ancestors 'none'",
    )
)

#: The prefix of the OpenAPI UI pages, which are exempt from the CSP (see the module docstring).
CSP_EXEMPT_PREFIX = "/schema"

#: The headers every response carries, whatever its media type. ``X-Frame-Options`` repeats
#: ``frame-ancestors`` for a browser that predates CSP2, and the duplication is the compatibility
#: measure, not a second policy. ``X-Content-Type-Options`` used to be set on the thumbnail route
#: alone; one definition is here now, and the thumbnail no longer carries its own.
STATIC_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def is_csp_exempt(path: str) -> bool:
    """Whether ``path`` is one of the documentation pages. Boundary-aware: ``/schemafoo`` is not."""
    return path == CSP_EXEMPT_PREFIX or path.startswith(f"{CSP_EXEMPT_PREFIX}/")


def headers_for(path: str) -> dict[str, str]:
    """The header set of one response, which is the policy plus the deployment's HSTS choice."""
    headers = dict(STATIC_HEADERS)
    if not is_csp_exempt(path):
        headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    hsts_seconds = get_settings().SECURITY_HSTS_SECONDS
    if hsts_seconds > 0:
        # No ``includeSubDomains`` and no ``preload``: both bind names outside this application,
        # and an operator cannot undo them from a configuration file once a browser has cached them.
        headers["Strict-Transport-Security"] = f"max-age={hsts_seconds}"
    return headers


class SecurityHeadersMiddleware(ASGIMiddleware):
    """Adds the policy to the ``http.response.start`` of every response, including refusals."""

    scopes = (ScopeType.HTTP,)

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        headers = headers_for(str(scope.get("path") or ""))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableScopeHeaders.from_message(message)
                for name, value in headers.items():
                    response_headers[name] = value
            await send(message)

        await next_app(scope, receive, send_with_headers)
