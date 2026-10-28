"""The session: signing in, signing out, and the account's own password.

The login route is the only one in the API that answers ``PUBLIC`` and writes something a person can
use — a session cookie. The cookie is ``HttpOnly`` and ``SameSite=Lax``, and ``Secure`` is
**configuration and not a constant**: over plain HTTP on a LAN the browser drops a ``Secure`` cookie
silently, so the login would look like it worked while nothing was stored (see
``AUTH_COOKIE_SECURE``).

Nothing here decides anything: the service owns the policy (the decoy verification, the sliding
session, which sessions end when a password changes), and this module is the translation between that
policy and HTTP — a cookie in, a cookie out, and the sentences the screen shows.
"""

from litestar import Controller, Request, Response, get, patch, post
from litestar.di import NamedDependency, Provide

from scrinalia.api.dependencies import (
    provide_auth_service,
    provide_current_user,
    provide_login_rate_limiter,
)
from scrinalia.api.login_rate_limit import LoginRateLimiter
from scrinalia.api.security import PASSWORD_CHANGE_EXEMPT_OPT_KEY, Access, AuthenticatedUser
from scrinalia.api.session_cookie import write_session_cookie
from scrinalia.core.config import get_settings
from scrinalia.domains.archive.schemas.responses import RouteMessageCode, RouteResponse
from scrinalia.domains.archive.schemas.route_messages import route_message
from scrinalia.domains.identity.schemas.auth_schema import LoginCommand
from scrinalia.domains.identity.schemas.user_schema import AuthUserDTO, ChangePasswordCommand, UpdateLocaleCommand
from scrinalia.domains.identity.services.auth_service import AuthService


class AuthController(Controller):
    """Sign-in and the account's own credentials. There is no self-service password recovery."""

    path = "/api/v1/auth"
    tags = ["Auth"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "auth_service": Provide(provide_auth_service, sync_to_thread=False),
        "current_user": Provide(provide_current_user, sync_to_thread=False),
        "login_rate_limiter": Provide(provide_login_rate_limiter, sync_to_thread=False),
    }

    @post("/login", opt={"access": Access.PUBLIC}, sync_to_thread=True)
    def login(
        self,
        auth_service: NamedDependency[AuthService],
        login_rate_limiter: NamedDependency[LoginRateLimiter],
        request: Request,
        data: LoginCommand,
    ) -> Response[AuthUserDTO]:
        """
        Opens a session and hands back the account.

        The answer is the account, not a sentence: the screen needs to know the name and the role to
        draw the shell, and a message would make it ask again. The per-address brake runs **before**
        the hash check, so an address walking the account list pays nothing to be refused, while the
        per-account lockout is decided inside the service, after the password was verified.
        """
        login_rate_limiter.check(request.client.host if request.client else "unknown")
        token, user = auth_service.login(
            data.email,
            data.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        response: Response[AuthUserDTO] = Response(AuthUserDTO.model_validate(user), status_code=200)
        write_session_cookie(response, token)
        return response

    @post(
        "/logout",
        opt={"access": Access.AUTHENTICATED, PASSWORD_CHANGE_EXEMPT_OPT_KEY: True},
        status_code=200,
        sync_to_thread=True,
    )
    def logout(
        self,
        auth_service: NamedDependency[AuthService],
        request: Request,
    ) -> Response[RouteResponse]:
        """
        Ends the session the cookie names.

        It requires a session — an anonymous caller gets 401 — because the alternative, declaring it
        public so it can always clear the cookie, would let any page sign the archivist out with a
        cross-site form post. A cookie left behind in the browser is harmless: the session behind it
        is already over.

        Exempt from the forced password change: the screen the flag forces the person onto still has
        to be able to sign out.
        """
        token = request.cookies.get(get_settings().AUTH_SESSION_COOKIE_NAME)
        if token:
            auth_service.logout(token)

        response: Response[RouteResponse] = Response(
            RouteResponse(
                code=RouteMessageCode.SESSION_ENDED,
                message=route_message(RouteMessageCode.SESSION_ENDED, "Sessão encerrada."),
            )
        )
        response.delete_cookie(get_settings().AUTH_SESSION_COOKIE_NAME)
        return response

    @get("/me", opt={"access": Access.AUTHENTICATED, PASSWORD_CHANGE_EXEMPT_OPT_KEY: True}, sync_to_thread=True)
    def me(
        self,
        auth_service: NamedDependency[AuthService],
        current_user: NamedDependency[AuthenticatedUser],
    ) -> AuthUserDTO:
        """
        The account behind the session, read fresh from the database.

        Fresh and not from the gate's snapshot because this is the *read contract*: the screen shows
        when the person last signed in and whether they still owe a password change, and a snapshot
        taken before the request could lag a change made by an administrator a second earlier.

        Exempt from the forced password change because it is how the forced screen learns that it is
        forced: refusing it would leave the account with no way to reach the very change it owes.
        """
        return AuthUserDTO.model_validate(auth_service.get_user(current_user.user_id))

    @patch("/me", opt={"access": Access.AUTHENTICATED}, sync_to_thread=True)
    def update_me(
        self,
        auth_service: NamedDependency[AuthService],
        current_user: NamedDependency[AuthenticatedUser],
        data: UpdateLocaleCommand,
    ) -> AuthUserDTO:
        """
        Stores the account's own interface language.

        ``locale: null`` means automatic: the SPA follows the browser, exactly as it does before a
        session exists. The answer is the account, so the shell can draw the choice it just made
        without a second request.
        """
        return AuthUserDTO.model_validate(auth_service.set_locale(current_user.user_id, data.locale))

    @post(
        "/password",
        opt={"access": Access.AUTHENTICATED, PASSWORD_CHANGE_EXEMPT_OPT_KEY: True},
        status_code=200,
        sync_to_thread=True,
    )
    def change_password(
        self,
        auth_service: NamedDependency[AuthService],
        current_user: NamedDependency[AuthenticatedUser],
        request: Request,
        data: ChangePasswordCommand,
    ) -> Response[RouteResponse]:
        """
        Replaces the account's own password, proving the current one.

        The session that makes the change survives it; every other one ends. Being logged out of the
        screen you are standing on, right after securing your account, is the behaviour that makes
        people avoid changing their password.

        Exempt from the forced password change by definition: it is the operation the refusal asks
        for, and the one that clears ``must_change_password``.
        """
        user = auth_service.get_user(current_user.user_id)
        auth_service.change_password(
            user,
            data.current_password,
            data.new_password,
            keep_token=request.cookies.get(get_settings().AUTH_SESSION_COOKIE_NAME),
        )
        return Response(
            RouteResponse(
                code=RouteMessageCode.PASSWORD_CHANGED,
                message=route_message(
                    RouteMessageCode.PASSWORD_CHANGED, "Senha alterada. As outras sessões desta conta foram encerradas."
                ),
            )
        )
