"""Every operation of ``/api/v1`` declares how it may be reached, and the declarations are a partition.

The point of this test is the same one ADR 0003 makes about the public projection: security by "remember
to protect the new route" is not auditable, and a missing guard fails silently — the route simply
works for everybody. So the classification is data on the route, and this walks the built application
and fails when an operation is left without one. A new route cannot ship unprotected by accident; it
can only ship *deliberately*, by adding a line somebody has to read in a diff.

The same walk pins the **second** rule the guard enforces: the account whose password is still the
temporary one the CLI printed reaches only the three operations the forced change needs. Declaring
that exemption is the one way in, and this file is what makes it visible.

It walks the **built** app inside a ``TestClient``, because ``route.route_handlers`` and each
handler's ``opt`` only exist after the router has been assembled.
"""

from collections import Counter
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from litestar.connection import ASGIConnection
from litestar.handlers.base import BaseRouteHandler
from litestar.testing import TestClient

from scrinalia.api.security import (
    PASSWORD_CHANGE_EXEMPT_OPT_KEY,
    PASSWORD_CHANGE_REQUIRED_MESSAGE,
    Access,
    AuthenticatedUser,
    PasswordChangeRequiredException,
    access_guard,
    access_of,
    is_password_change_exempt,
)
from scrinalia.asgi import create_app
from scrinalia.core.config import get_settings
from scrinalia.domains.archive.schemas.responses import RouteMessageCode
from scrinalia.domains.identity.domain.permissions import Permission, Role

#: The operations reachable without a session, pinned as a list. This is the open surface of the
#: installation: the diffusion routes (open by design, ADR 0003), the login that creates a session,
#: and the two first-run operations that bring an empty installation to life (ADR 0011). Anything
#: else appearing here is a decision, not an oversight.
#:
#: The setup pair was added **deliberately**: the write is guarded by a table lock and the predicate
#: "``auth_users`` is empty", so it answers 409 forever once any account exists — the surface grows by
#: two operations and the growth is this line, in a diff.
PUBLIC_OPERATIONS = {
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/setup/status"),
    ("POST", "/api/v1/setup/admin"),
    ("GET", "/api/v1/public/documents"),
    ("GET", "/api/v1/public/documents/{description_id:str}"),
}

#: The POSTs that only compute. Declared ``AUTHENTICATED`` on purpose — the permission is about what a
#: request can *change*, and a dry run, a preview or a proposal changes nothing — so they are pinned
#: here: a writing route that lands in this set has to be added to it, in a diff, by hand.
#:
#: ``logout`` and ``password`` are here for a different reason and it matters: they do write, but they
#: write about **your own** account, and a ``VIEWER`` who cannot end their own session or replace a
#: password an administrator handed them is not a security model, it is a trap.
READ_ONLY_POSTS = {
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password"),
    ("POST", "/api/v1/hierarchy/materialisation/preview"),
    ("POST", "/api/v1/hierarchy/proposal"),
    ("POST", "/api/v1/quality/cleaning-rules/preview"),
    ("POST", "/api/v1/quality/text-templates/preview"),
    ("POST", "/api/v1/taxonomy/conflicts/resolve/preview"),
    ("POST", "/api/v1/taxonomy/entities/merge/preview"),
    ("POST", "/api/v1/taxonomy/entities/ner-exclusions/purge/preview"),
    ("POST", "/api/v1/taxonomy/tags/merge/preview"),
    ("POST", "/api/v1/taxonomy/tags/subject-exclusions/preview"),
    ("POST", "/api/v1/taxonomy/tags/stopwords/purge/preview"),
    # Computes candidates for the subject axis and writes nothing; the route that *applies* a
    # suggestion carries its own permission. It was the one read-only POST classified as a write.
    ("POST", "/api/v1/taxonomy/tags/suggest-macro"),
}

#: Litestar's auto-generated preflight handler is not an operation of this API and carries no
#: classification; the guard skips ``OPTIONS`` for the same reason.
IGNORED_METHODS = {"OPTIONS"}

#: The operations reachable while the account still owes the **forced password change**. The rule
#: lives in ``security.access_guard`` and refuses everything else; this pins the exception, so the
#: next route lands inside the rule and widening it is a line a reviewer reads. ``me``/``logout`` are
#: the ways out the forced screen stands on and ``password`` is the change itself.
PASSWORD_CHANGE_EXEMPT_OPERATIONS = {
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password"),
}


def _operation_handlers() -> list[tuple[str, str, BaseRouteHandler]]:
    """Every classified operation of ``/api/v1`` as ``(method, path, route_handler)``."""
    app = create_app()
    rows: list[tuple[str, str, BaseRouteHandler]] = []
    with TestClient(app=app):
        for route in app.routes:
            path = str(getattr(route, "path", ""))
            if not path.startswith("/api/v1"):
                continue
            for route_handler in getattr(route, "route_handlers", []) or []:
                for method in route_handler.http_methods:
                    if str(method) in IGNORED_METHODS:
                        continue
                    rows.append((str(method), path, route_handler))
    return rows


def _operations() -> list[tuple[str, str, Access | None]]:
    """Every classified operation of ``/api/v1`` as ``(method, path, access)``."""
    return [(method, path, access_of(handler)) for method, path, handler in _operation_handlers()]


def test_the_walk_actually_sees_the_api() -> None:
    """A walk that matched nothing would make every assertion below pass for the wrong reason."""
    assert len(_operations()) >= 100


def test_every_operation_declares_an_access_level() -> None:
    unclassified = sorted((method, path) for method, path, access in _operations() if access is None)

    assert unclassified == [], (
        f"these operations of /api/v1 declare no access level: {unclassified}. "
        'Add opt={"access": Access.X} to the route decorator.'
    )


def test_the_declared_levels_are_the_ones_the_map_knows() -> None:
    """A value the enum does not know is treated as unclassified at runtime; it must not be declared."""
    known = {access for _, _, access in _operations() if access is not None}
    assert known <= set(Access)


def test_the_open_surface_is_exactly_the_diffusion_and_the_login() -> None:
    public = sorted((method, path) for method, path, access in _operations() if access is Access.PUBLIC)

    assert set(public) == PUBLIC_OPERATIONS


def test_only_the_declared_read_only_posts_escape_a_write_permission() -> None:
    """
    The property that matters most, stated as a set: a POST that writes must not be ``AUTHENTICATED``.

    Without this, a new mutation route added with the default level would be reachable by any reader,
    and the partition test above would still be green.
    """
    authenticated_posts = {
        (method, path) for method, path, access in _operations() if method == "POST" and access is Access.AUTHENTICATED
    }

    assert authenticated_posts == READ_ONLY_POSTS


def test_the_two_vocabularies_cannot_drift() -> None:
    """``Access`` is the four permissions plus the two levels below them, and nothing else."""
    assert {access.value for access in Access} - {"PUBLIC", "AUTHENTICATED"} == {
        permission.value for permission in Permission
    }


def test_the_classification_is_not_a_rubber_stamp() -> None:
    """
    A regression that declared everything ``AUTHENTICATED`` would satisfy the partition test.

    The counts are asserted as a floor per level, not as an exact map: the exact map is the code, and
    pinning it here would make every new route edit two files. What must not happen is a level that
    silently empties.
    """
    counts = Counter(access for _, _, access in _operations() if access is not None)

    assert counts[Access.AUTHENTICATED] > 0
    assert counts[Access.CURATE] > 0
    assert counts[Access.CATALOGUE] > 0
    assert counts[Access.OPERATE] > 0


# --- The temporary credential (issue #79) --------------------------------------------------------


def test_the_forced_password_change_exempts_exactly_the_ways_out() -> None:
    """
    The exemption is a closed set, read from the routes themselves.

    This is the ``opt`` half of the rule the guard enforces: if a route declares the exemption and
    this set does not list it, the diff has to say why; if the set lists one the routes do not
    declare, the guard would refuse a way out the forced screen needs.
    """
    exempt = sorted(
        (method, path) for method, path, handler in _operation_handlers() if is_password_change_exempt(handler)
    )

    assert set(exempt) == PASSWORD_CHANGE_EXEMPT_OPERATIONS


def test_an_exempt_operation_still_requires_a_session() -> None:
    """The exemption is from the password gate, not from authentication: none of the three is public."""
    levels = {access for method, path, access in _operations() if (method, path) in PASSWORD_CHANGE_EXEMPT_OPERATIONS}

    assert levels == {Access.AUTHENTICATED}


def _run_guard(*, must_change_password: bool, opt: dict[str, object]) -> None:
    """
    Runs the guard once for a signed-in account, with only the two inputs the decision reads faked.

    ``resolve_authenticated_user`` is patched at its use site because the guard calls it as a module
    global; the connection and the route handler are the minimal duck-typed shapes ``access_guard``
    touches — the scope it classifies, the cookie it reads, and the ``opt`` it checks.
    """
    user = AuthenticatedUser(
        user_id=1,
        email="maria@arquivo.org",
        name="Maria",
        role=Role.CURATOR,
        must_change_password=must_change_password,
    )
    scope: dict[str, Any] = {"type": "http", "method": "GET", "path": "/api/v1/curation/inbox"}
    connection = cast(
        ASGIConnection,
        SimpleNamespace(scope=scope, cookies={get_settings().AUTH_SESSION_COOKIE_NAME: "token"}),
    )
    handler = cast(BaseRouteHandler, SimpleNamespace(opt=opt))

    with patch("scrinalia.api.security.resolve_authenticated_user", return_value=user):
        access_guard(connection, handler)


def test_an_ordinary_route_is_refused_while_the_password_is_temporary() -> None:
    with pytest.raises(PasswordChangeRequiredException) as refusal:
        _run_guard(must_change_password=True, opt={"access": Access.AUTHENTICATED})

    assert refusal.value.code is RouteMessageCode.PASSWORD_CHANGE_REQUIRED
    assert str(refusal.value.detail) == PASSWORD_CHANGE_REQUIRED_MESSAGE


def test_the_refusal_is_named_before_the_permission_is_even_consulted() -> None:
    """
    A temporary credential is refused as such on a route the role could not reach anyway.

    The order matters for the sentence the person reads: "change the password" is actionable, "your
    role may not do this" is not — and a ``CURATOR`` on an ``ADMIN`` route would otherwise get the
    second one and go looking for a permission problem that is not there.
    """
    with pytest.raises(PasswordChangeRequiredException):
        _run_guard(must_change_password=True, opt={"access": Access.ADMIN})


def test_the_same_route_is_reachable_once_the_password_changed() -> None:
    """The flag is the whole difference: the same route and the same role, and no refusal."""
    _run_guard(must_change_password=False, opt={"access": Access.AUTHENTICATED})


def test_the_exempt_routes_stay_reachable_while_the_password_is_temporary() -> None:
    _run_guard(
        must_change_password=True,
        opt={"access": Access.AUTHENTICATED, PASSWORD_CHANGE_EXEMPT_OPT_KEY: True},
    )
