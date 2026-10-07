"""Who reaches a route: one guard that answers both questions, from the route's own declaration.

Every operation of ``/api/v1`` declares how it may be reached with ``opt={"access": Access.X}``, and a
**single guard** registered on the application enforces it. One key and one enforcement point for a
hundred operations, instead of a guard per route: Litestar guards are cumulative and a route cannot
relax what its controller declared, so a guard placed on a controller would leak into the reads a
``VIEWER`` must reach. The classification is therefore per handler, and
``testing/unit/api/test_route_access.py`` fails when an operation is left without one — "remember to
protect the new route" is a build error here, not a process.

The guard does the authentication *and* the authorization, and that is deliberate rather than
convenient. A middleware would run outside Litestar's exception-handler layer, so its 401 would be
produced after the request-context middleware had already logged the access line — the answer the
front sees most often would be the one line in the log with no status and no ``X-Request-ID``. A
guard runs inside the route handler, before the handler body and before dependency resolution, so it
refuses just as early *and* the refusal is correlated like every other answer.

The two failures are ``HTTPException`` on purpose (``NotAuthorizedException`` and
``PermissionDeniedException``), never a ``DomainException``: the unhandled-failure ledger records
*defects*, and a 401 or a 403 is an answer the API owes the client. A domain exception would also be
mapped to a 400 by the domain handler, which is the wrong sentence for the wrong situation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.handlers.base import BaseRouteHandler
from litestar.types import Scope

from scrinalia.core.config import get_settings
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.domains.identity.domain.permissions import Permission, Role, has_permission
from scrinalia.domains.identity.repository.session_repo import SessionRepository
from scrinalia.domains.identity.repository.user_repo import UserRepository
from scrinalia.domains.identity.services.auth_service import AuthService

#: The route ``opt`` key that carries the classification. One key, read by the guard and by the
#: partition test, so "what does this route require?" has exactly one answer per operation.
ACCESS_OPT_KEY = "access"

#: The only prefix the guard touches. ``/health/*``, ``/schema*`` and the SPA are outside it by
#: construction, which is why the orchestrator's probes and the OpenAPI document need no exception.
API_PREFIX = "/api/v1"

SESSION_REQUIRED_MESSAGE = "É preciso entrar para acessar o sistema."
PERMISSION_DENIED_MESSAGE = "Sua conta não tem permissão para esta ação."
UNCLASSIFIED_ROUTE_MESSAGE = "Rota sem classificação de acesso."


class Access(enum.StrEnum):
    """
    How a route may be reached: the four permissions, plus the two levels below them.

    ``PUBLIC`` is the only one that means "no session at all" — the diffusion surface and the login
    route. ``AUTHENTICATED`` is "any account that can sign in": every read, and the read-only POSTs
    (the dry runs, the previews, the proposal) that compute something and write nothing.
    """

    PUBLIC = "PUBLIC"
    AUTHENTICATED = "AUTHENTICATED"
    CURATE = "CURATE"
    CATALOGUE = "CATALOGUE"
    OPERATE = "OPERATE"
    ADMIN = "ADMIN"


@dataclass(frozen=True)
class AuthenticatedUser:
    """
    The signed-in account, as one request carries it.

    A frozen snapshot and **not** the ORM row: the session is resolved in its own short transaction
    (it may slide ``last_seen_at``), which is closed before the handler runs. Passing the row along
    would hand the request a detached instance whose attributes expire on commit — a
    ``DetachedInstanceError`` waiting for the first handler that reads ``user.role``.
    """

    user_id: int
    email: str
    name: str
    role: Role
    must_change_password: bool


def authenticated_user_of(scope: Scope) -> AuthenticatedUser | None:
    """The account the guard put in the scope, or ``None`` when nobody is signed in."""
    user = scope.get("user")
    return user if isinstance(user, AuthenticatedUser) else None


def access_of(route_handler: BaseRouteHandler | None) -> Access | None:
    """
    The classification a route declares, or ``None`` when it declares nothing.

    A value the enum does not know is treated as *unclassified* rather than raising: a typo must deny
    the route, and the partition test is what turns the typo into a build failure.
    """
    if route_handler is None:
        return None
    raw = route_handler.opt.get(ACCESS_OPT_KEY)
    if raw is None:
        return None
    try:
        return Access(raw)
    except ValueError:
        return None


def resolve_authenticated_user(token: str) -> AuthenticatedUser | None:
    """
    Resolves a session token to the account it identifies.

    Its own short session, committed: ``AuthService.resolve_session`` slides ``expires_at`` when the
    session has been idle, and that write belongs to the request that used the session — it must not
    be rolled back by a handler that fails later, nor held open for the duration of the request.
    """
    with get_db() as db:
        service = AuthService(UserRepository(db), SessionRepository(db))
        user = service.resolve_session(token)
        if user is None:
            return None
        snapshot = AuthenticatedUser(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
            role=user.role,
            must_change_password=user.must_change_password,
        )
        db.commit()
        return snapshot


def _is_preflight(scope: Scope) -> bool:
    """``OPTIONS`` is Litestar's own auto-generated handler; it must never require a session."""
    return str(scope.get("method") or "").upper() == "OPTIONS"


def access_guard(connection: ASGIConnection, route_handler: BaseRouteHandler) -> None:
    """
    Authenticates and authorizes the request, in that order, from the route's declaration.

    Routes outside ``/api/v1`` are neither classified nor guarded — the SPA shell, the health probes
    and the OpenAPI document are reached without a session and are not this guard's business.
    """
    scope = connection.scope
    if _is_preflight(scope) or not str(scope.get("path") or "").startswith(API_PREFIX):
        return

    access = access_of(route_handler)
    if access is None:
        # Unreachable while the partition test passes; if it ever runs, the answer is "no" and the
        # log names the handler, so the fix is one line instead of a hunt.
        logger.warning(f"🔒 Rota sem classificação de acesso: {scope.get('method')} {scope.get('path')}")
        raise PermissionDeniedException(UNCLASSIFIED_ROUTE_MESSAGE)

    if access is Access.PUBLIC:
        return

    token = connection.cookies.get(get_settings().AUTH_SESSION_COOKIE_NAME)
    user = resolve_authenticated_user(token) if token else None
    if user is None:
        raise NotAuthorizedException(SESSION_REQUIRED_MESSAGE)

    # Published for the handlers: ``provide_current_user`` reads it, and it is the *only* place the
    # account comes from, so a handler cannot disagree with the authorization that just ran.
    scope["user"] = user

    if access is Access.AUTHENTICATED:
        return

    if not has_permission(user.role, Permission(access.value)):
        raise PermissionDeniedException(PERMISSION_DENIED_MESSAGE)
