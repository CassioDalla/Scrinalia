"""Request correlation and the access line.

Every request leaves with an ``X-Request-ID``: the one the client sent, or a generated one. The same
value is bound to the log context, so **every** record emitted while the request is being served —
including the one the unhandled-exception handler writes — carries it in ``record.extra`` of
``ui_stream.jsonl``. That is what turns "quebrou às 14:32" into a grep.

The access line is emitted here instead of relying on uvicorn's, because uvicorn's record has no
request id and cannot: the id is minted inside the ASGI application. The two health probes are
excluded, and that exclusion is not cosmetic — an orchestrator asks every few seconds, and logging
each one would rotate a 50 MB file with nothing but "200 OK".
"""

from __future__ import annotations

import re
import time
from typing import Any
from uuid import uuid4

from litestar.datastructures import Headers, MutableScopeHeaders
from litestar.enums import ScopeType
from litestar.middleware import ASGIMiddleware
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from scrinalia.core.logger import logger

#: The header a client may send and always receives back. Lowercase: ASGI stores header names that
#: way, and the comparison is case-insensitive on both ends.
REQUEST_ID_HEADER = "x-request-id"

#: A client-supplied id is echoed into a response header and written to the log, so it is accepted
#: only if it looks like an id: bounded in length and free of anything that could forge a log line
#: or split a header.
MAX_REQUEST_ID_LENGTH = 64
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]+$")

#: The orchestrator's probes. They are excluded from the access line, never from correlation.
QUIET_PATHS = frozenset({"/health/live", "/health/ready"})


def request_id_of(scope: Scope) -> str | None:
    """The id bound to this request, for whoever needs to record it next to a failure."""
    state: Any = scope.get("state")
    return state.get("request_id") if isinstance(state, dict) else None


def _accept_request_id(scope: Scope) -> str | None:
    raw = Headers.from_scope(scope).get(REQUEST_ID_HEADER)
    if raw is not None and len(raw) <= MAX_REQUEST_ID_LENGTH and SAFE_REQUEST_ID.match(raw):
        return raw
    return None


class RequestContextMiddleware(ASGIMiddleware):
    """
    Mints or accepts a request id, echoes it, and writes the access line.

    Stateless on purpose: Litestar builds the instance once and shares it across every request, so
    anything request-specific lives in ``handle``.
    """

    scopes = (ScopeType.HTTP,)

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        request_id = _accept_request_id(scope) or uuid4().hex

        state = scope.get("state")
        if not isinstance(state, dict):
            state = {}
            scope["state"] = state
        state["request_id"] = request_id

        started = time.perf_counter()
        status_code: int | None = None

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableScopeHeaders.from_message(message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        with logger.contextualize(request_id=request_id):
            try:
                await next_app(scope, receive, send_with_request_id)
            finally:
                self._log_access(scope, status_code, started)

    def _log_access(self, scope: Scope, status_code: int | None, started: float) -> None:
        path = str(scope.get("path") or "")
        if path in QUIET_PATHS:
            return

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        method = str(scope.get("method") or "?")
        line = f"{method} {path} -> {status_code} em {duration_ms} ms"

        # 5xx is the line somebody greps for, so it is a warning; an unhandled failure has already
        # been logged with its traceback by the handler, which is where the detail belongs.
        if status_code is not None and status_code >= 500:
            logger.warning(f"❌ {line}")
        else:
            logger.info(f"↔️ {line}")
