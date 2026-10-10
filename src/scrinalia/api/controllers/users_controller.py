"""The accounts of the installation: who exists, what they may do, and where they are signed in.

This is the surface of ``Permission.ADMIN``, and it is deliberately its own controller rather than a
corner of ``AuthController``. ``/auth`` answers *"who am I?"* and lets a person manage **their own**
credentials; ``/users`` answers *"who else is there?"* and lets an administrator manage other
people's. Filing them together would put the route that can deactivate an account beside the route
that a ``VIEWER`` must reach to end their own session, and the two would share a prefix while
requiring different permissions.

Nothing here hashes a password or decides a policy: the service owns all of it, and this module is the
translation between that policy and HTTP. Two rules are worth stating because they are easy to undo:
the account being edited is **never** taken from the body (it is the path id, and the last-admin guard
reads the row the service loaded), and a reset password is always temporary — the administrator chose
it, so the account has to replace it at the next sign-in.
"""

from litestar import Controller, Request, Response, delete, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath

from scrinalia.api.dependencies import provide_auth_service, provide_current_user
from scrinalia.api.security import Access, AuthenticatedUser
from scrinalia.core.config import get_settings
from scrinalia.domains.archive.schemas.responses import RouteMessageCode, RouteResponse
from scrinalia.domains.identity.domain.credentials import hash_session_token
from scrinalia.domains.identity.schemas.user_schema import (
    AuthSessionDTO,
    AuthUserDTO,
    CreateUserCommand,
    SetPasswordCommand,
    UpdateUserCommand,
)
from scrinalia.domains.identity.services.auth_service import AuthService


class UsersController(Controller):
    """Account administration: create, edit, deactivate, reset a password and end sessions."""

    path = "/api/v1/users"
    tags = ["Users"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "auth_service": Provide(provide_auth_service, sync_to_thread=False),
        "current_user": Provide(provide_current_user, sync_to_thread=False),
    }

    @get("/", opt={"access": Access.ADMIN}, sync_to_thread=True)
    def list_users(self, auth_service: NamedDependency[AuthService]) -> list[AuthUserDTO]:
        """
        Every account, deactivated ones included.

        The whole installation in one read: the screen's question is "who has an account?", and a
        page of accounts would answer a question nobody asked while hiding the deactivated ones that
        explain why somebody cannot sign in.
        """
        return [AuthUserDTO.model_validate(user) for user in auth_service.list_users()]

    @post("/", opt={"access": Access.ADMIN}, status_code=201, sync_to_thread=True)
    def create_user(
        self,
        auth_service: NamedDependency[AuthService],
        data: CreateUserCommand,
    ) -> AuthUserDTO:
        """
        Creates an account with the password the administrator typed.

        ``must_change_password`` is set: the administrator knows this password, so it is temporary by
        construction, exactly like the one the CLI prints. The account replaces it at the first
        sign-in, and until then the screens stay out of reach.
        """
        user = auth_service.create_user(data, must_change_password=True)
        return AuthUserDTO.model_validate(user)

    @patch("/{user_id:int}", opt={"access": Access.ADMIN}, sync_to_thread=True)
    def update_user(
        self,
        auth_service: NamedDependency[AuthService],
        user_id: FromPath[int],
        data: UpdateUserCommand,
    ) -> AuthUserDTO:
        """
        Renames, re-roles or (de)activates an account.

        Two consequences the screen has to state, both enforced in the service: losing the last active
        administrator is refused, and deactivating ends every session of the account immediately — the
        flag alone would let whoever holds the cookie keep working until it expired.
        """
        user = auth_service.get_user(user_id)
        return AuthUserDTO.model_validate(auth_service.update_user(user, data))

    @post("/{user_id:int}/password", opt={"access": Access.ADMIN}, status_code=200, sync_to_thread=True)
    def reset_password(
        self,
        auth_service: NamedDependency[AuthService],
        user_id: FromPath[int],
        data: SetPasswordCommand,
    ) -> Response[RouteResponse]:
        """
        An administrator sets a password without knowing the old one.

        Every session of the account ends with it, which is the point: a reset is what an
        administrator does when somebody lost access, and leaving the old devices signed in would
        answer that with nothing. Unlike ``change_password`` there is no ``keep_token`` here, so an
        administrator who resets **their own** account ends the session the request arrived on — the
        accounts screen says so before the click, and points at "Trocar senha" for the case where the
        person does know the current password and merely wants to replace it.
        """
        user = auth_service.get_user(user_id)
        auth_service.reset_password(user, data.password, must_change=data.must_change)
        return Response(
            RouteResponse(
                code=RouteMessageCode.USER_PASSWORD_RESET,
                message="Senha redefinida. As sessões desta conta foram encerradas.",
            )
        )

    @get("/{user_id:int}/sessions", opt={"access": Access.ADMIN}, sync_to_thread=True)
    def list_sessions(
        self,
        auth_service: NamedDependency[AuthService],
        current_user: NamedDependency[AuthenticatedUser],
        request: Request,
        user_id: FromPath[int],
    ) -> list[AuthSessionDTO]:
        """
        Where this account is signed in, most recently seen first.

        The row that is *this* request's own session is marked, because "sign out everywhere" is a
        button somebody presses while standing on a screen, and ending the session they are using is a
        decision they should see coming.
        """
        token = request.cookies.get(get_settings().AUTH_SESSION_COOKIE_NAME)
        current_hash = hash_session_token(token) if token else None
        sessions = auth_service.list_sessions(user_id)
        return [
            AuthSessionDTO.model_validate(session).model_copy(update={"is_current": session.token_hash == current_hash})
            for session in sessions
        ]

    @delete("/{user_id:int}/sessions", opt={"access": Access.ADMIN}, status_code=200, sync_to_thread=True)
    def revoke_all_sessions(
        self,
        auth_service: NamedDependency[AuthService],
        user_id: FromPath[int],
    ) -> Response[RouteResponse]:
        """Ends every session of the account — the "sign out everywhere" of a lost laptop."""
        ended = auth_service.revoke_all_sessions(user_id)
        return Response(
            RouteResponse(
                code=RouteMessageCode.USER_SESSIONS_REVOKED,
                message=f"{ended} sessão(ões) encerrada(s).",
            )
        )

    @delete(
        "/{user_id:int}/sessions/{session_id:int}",
        opt={"access": Access.ADMIN},
        status_code=200,
        sync_to_thread=True,
    )
    def revoke_session(
        self,
        auth_service: NamedDependency[AuthService],
        user_id: FromPath[int],
        session_id: FromPath[int],
    ) -> Response[RouteResponse]:
        """
        Ends one session.

        A session id that belongs to another account answers 404 and not 200: the id is the only thing
        the request carries, and confirming it exists elsewhere would enumerate other people's
        sign-ins.
        """
        auth_service.revoke_session(user_id, session_id)
        return Response(RouteResponse(code=RouteMessageCode.SESSION_REVOKED, message="Sessão encerrada."))
