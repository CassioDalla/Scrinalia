"""The one place the session cookie is written.

Two routes hand out a session — the login and the first-run setup (ADR 0011) — and the cookie's
attributes are a security decision, not a formatting detail: ``HttpOnly`` keeps scripts away from the
token, ``SameSite=Lax`` is what a same-origin SPA needs, and ``Secure`` is **configuration and not a
constant** because a browser drops a ``Secure`` cookie over plain HTTP silently, which would make the
login look like it worked while nothing was stored. A second copy of these five lines in the setup
controller is a second place for that decision to be wrong.
"""

from litestar import Response

from scrinalia.core.config import get_settings


def write_session_cookie(response: Response, token: str) -> None:
    """Puts the raw session token in the cookie, with the attributes the deployment declares."""
    current = get_settings()
    response.set_cookie(
        key=current.AUTH_SESSION_COOKIE_NAME,
        value=token,
        max_age=current.AUTH_SESSION_TTL_MINUTES * 60,
        path="/",
        httponly=True,
        secure=current.AUTH_COOKIE_SECURE,
        samesite="lax",
    )
