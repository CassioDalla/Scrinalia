"""Every operation of ``/api/v1`` declares how it may be reached, and the declarations are a partition.

The point of this test is the same one ADR 0003 makes about the public projection: security by "remember
to protect the new route" is not auditable, and a missing guard fails silently — the route simply
works for everybody. So the classification is data on the route, and this walks the built application
and fails when an operation is left without one. A new route cannot ship unprotected by accident; it
can only ship *deliberately*, by adding a line somebody has to read in a diff.

It walks the **built** app inside a ``TestClient``, because ``route.route_handlers`` and each
handler's ``opt`` only exist after the router has been assembled.
"""

from collections import Counter

from litestar.testing import TestClient

from scrinalia.api.security import Access, access_of
from scrinalia.asgi import create_app
from scrinalia.domains.identity.domain.permissions import Permission

#: The operations reachable without a session, pinned as a list. This is the open surface of the
#: installation: the diffusion routes (open by design, ADR 0003) and the login that creates a
#: session. Anything else appearing here is a decision, not an oversight.
PUBLIC_OPERATIONS = {
    ("POST", "/api/v1/auth/login"),
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
    ("POST", "/api/v1/taxonomy/tags/merge/preview"),
    ("POST", "/api/v1/taxonomy/tags/stopwords/purge/preview"),
    # Computes candidates for the subject axis and writes nothing; the route that *applies* a
    # suggestion carries its own permission. It was the one read-only POST classified as a write.
    ("POST", "/api/v1/taxonomy/tags/suggest-macro"),
}

#: Litestar's auto-generated preflight handler is not an operation of this API and carries no
#: classification; the guard skips ``OPTIONS`` for the same reason.
IGNORED_METHODS = {"OPTIONS"}


def _operations() -> list[tuple[str, str, Access | None]]:
    """Every classified operation of ``/api/v1`` as ``(method, path, access)``."""
    app = create_app()
    rows: list[tuple[str, str, Access | None]] = []
    with TestClient(app=app):
        for route in app.routes:
            path = str(getattr(route, "path", ""))
            if not path.startswith("/api/v1"):
                continue
            for route_handler in getattr(route, "route_handlers", []) or []:
                for method in route_handler.http_methods:
                    if str(method) in IGNORED_METHODS:
                        continue
                    rows.append((str(method), path, access_of(route_handler)))
    return rows


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
