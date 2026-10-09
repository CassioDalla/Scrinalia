"""Bringing an installation to life: whether it needs to, and the one call that does it.

Two operations, and they are the only ones in the API whose permission depends on **the data**: while
``auth_users`` is empty, an anonymous client may create the administrator, because otherwise the
installation can only be configured from a shell on the host. The permission is still declared once
per operation — ``Access.PUBLIC`` — and the *data* condition is the route's business logic, not a
second reading of the classification.

What keeps that from being an open door is the table lock in
``UserRepository.create_first_admin``: the predicate is evaluated under ``LOCK TABLE … IN EXCLUSIVE
MODE``, so two concurrent calls cannot both create an account and every call after the first answers
409 **forever** (ADR 0011). The ``origin_guard`` applies here like to any mutation, so a browser on
another site cannot claim an unconfigured instance with a cross-site form post.

This controller is separate from ``AuthController`` on purpose. ``/auth`` is "who am I?" for somebody
who already has an account; ``/setup`` is reachable by somebody who cannot have one yet. Filing them
together would put a route that only works on an empty database beside the route every deployment uses
every day.
"""

from litestar import Controller, Request, Response, get, post
from litestar.di import NamedDependency, Provide

from scrinalia.api.dependencies import provide_auth_service
from scrinalia.api.security import Access
from scrinalia.api.session_cookie import write_session_cookie
from scrinalia.domains.identity.schemas.setup_schema import (
    SetupFirstAdminCommand,
    SetupStatusResponse,
)
from scrinalia.domains.identity.schemas.user_schema import AuthUserDTO
from scrinalia.domains.identity.services.auth_service import AuthService


class SetupController(Controller):
    """The first run of an installation that has no account at all."""

    path = "/api/v1/setup"
    tags = ["Setup"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "auth_service": Provide(provide_auth_service, sync_to_thread=False),
    }

    @get("/status", opt={"access": Access.PUBLIC}, sync_to_thread=True)
    def status(self, auth_service: NamedDependency[AuthService]) -> SetupStatusResponse:
        """
        Whether the installation has to be configured.

        It answers a boolean and nothing else, deliberately: an installation with no accounts is not
        holding a secret, and the SPA has to decide which screen to draw *before* it has a session to
        ask with.
        """
        return SetupStatusResponse(needs_setup=auth_service.needs_setup())

    @post("/admin", opt={"access": Access.PUBLIC}, status_code=201, sync_to_thread=True)
    def create_admin(
        self,
        auth_service: NamedDependency[AuthService],
        request: Request,
        data: SetupFirstAdminCommand,
    ) -> Response[AuthUserDTO]:
        """
        Creates the first administrator and signs them in.

        The answer is the account, exactly like the login: the screen draws the shell from it without
        asking again. The cookie is the login's own, written by the one function that knows its
        attributes — and this is the only time this route ever hands one out, because after the first
        account exists it answers 409 and nothing else.
        """
        token, user = auth_service.create_first_admin(
            data,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        response: Response[AuthUserDTO] = Response(AuthUserDTO.model_validate(user), status_code=201)
        write_session_cookie(response, token)
        return response
