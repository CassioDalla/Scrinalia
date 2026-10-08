"""Who may reach what, end to end: the anonymous client, the three roles, and the two open surfaces.

The classification itself is pinned structurally in ``testing/unit/api/test_route_access.py``. What
this file adds is the *behaviour*: that the guard actually refuses, that it refuses with the right
status, and that the refusals do not leak what they should not. A classification test and a behaviour
test fail for different reasons, and a system where authorization is only asserted on paper is one
where a guard that never runs looks perfectly correct.
"""

import pytest
from litestar.testing import TestClient

from scrinalia.api.controllers import health_controller
from scrinalia.domains.identity.domain.permissions import Role
from scrinalia.domains.identity.schemas.user_schema import UpdateUserCommand

#: A route of each permission, chosen so the assertion is about the permission and not the route:
#: reading the collection, writing a closed catalogue, touching the worker panel.
READ_ROUTE = "/api/v1/documents"
CATALOGUE_ROUTE = "/api/v1/typologies"
OPERATE_ROUTE = "/api/v1/system/health"


# ==========================================
# THE ANONYMOUS CLIENT
# ==========================================


def test_an_anonymous_client_is_refused(api_client: TestClient) -> None:
    response = api_client.get(READ_ROUTE)

    assert response.status_code == 401
    assert response.json()["error_code"] == "NotAuthorizedException"
    assert response.json()["message"]


def test_the_refusal_carries_the_request_id(api_client: TestClient) -> None:
    """A 401 is the answer the front sees most often; it must be traceable like any other."""
    response = api_client.get(READ_ROUTE, headers={"X-Request-ID": "trace-401"})

    assert response.headers["x-request-id"] == "trace-401"


def test_the_diffusion_surface_answers_without_a_session(api_client: TestClient) -> None:
    """Open by design (ADR 0003): the boundary here is *what data exists*, not who is asking."""
    assert api_client.get("/api/v1/public/documents").status_code == 200


def test_the_health_probes_answer_without_a_session(api_client: TestClient, monkeypatch) -> None:
    """The orchestrator must not have to know the API version, let alone hold a session.

    The readiness probe owns an engine built from the ambient settings, so the database is pinned
    here rather than assumed. A literal 200 tied the test to whichever database the checkout pointed
    at: it passed in CI, where the job exports ``DB_*``, and failed on a machine whose ``.env`` names
    a database that does not exist. Pinning both answers is also the only way this test can see the
    503, which is the half an orchestrator actually acts on.
    """
    assert api_client.get("/health/live").status_code == 200

    monkeypatch.setattr(health_controller, "database_answers", lambda: True)
    assert api_client.get("/health/ready").status_code == 200

    monkeypatch.setattr(health_controller, "database_answers", lambda: False)
    assert api_client.get("/health/ready").status_code == 503


def test_the_api_document_answers_without_a_session(api_client: TestClient) -> None:
    assert api_client.get("/schema/openapi.json").status_code == 200


def test_an_unknown_path_is_not_an_authentication_question(api_client: TestClient) -> None:
    """
    A path with no route answers 404 and not 401.

    The guard runs per matched route, so "there is nothing here" stays what it is. Turning it into
    401 would tell a client with a typo to sign in, which is a worse answer than the truth.
    """
    assert api_client.get("/api/v1/nao-existe").status_code == 404


# ==========================================
# THE THREE ROLES
# ==========================================


def test_a_viewer_reads_but_does_not_write(sign_in) -> None:
    client = sign_in(Role.VIEWER)

    assert client.get(READ_ROUTE).status_code == 200
    assert client.post(CATALOGUE_ROUTE, json={"name": "Ata"}).status_code == 403


def test_a_viewer_cannot_operate_the_installation(sign_in) -> None:
    client = sign_in(Role.VIEWER)

    assert client.get(OPERATE_ROUTE).status_code == 403


def test_a_curator_curates_and_maintains_the_catalogues(sign_in) -> None:
    client = sign_in(Role.CURATOR)

    assert client.get(READ_ROUTE).status_code == 200
    # 201 proves the permission passed and the route did its work; the payload is the catalogue's
    # business, not this test's.
    assert client.post(CATALOGUE_ROUTE, json={"name": "Ata de Reunião"}).status_code == 201


def test_a_curator_cannot_operate_the_installation(sign_in) -> None:
    """
    The line that matters most in the map.

    Triggering a worker costs minutes of CPU and changing its preset changes every future
    classification, so a curation account must not reach the panel that does either.
    """
    client = sign_in(Role.CURATOR)

    assert client.get(OPERATE_ROUTE).status_code == 403
    assert client.put("/api/v1/system/workers/ner/settings", json={}).status_code == 403


def test_an_administrator_reaches_the_installation_panel(sign_in) -> None:
    client = sign_in(Role.ADMIN)

    # 404 (no such worker) and not 403: the permission passed and the *route* answered.
    assert client.put("/api/v1/system/workers/nao-existe/settings", json={}).status_code == 404


def test_a_refusal_is_403_and_not_404(sign_in) -> None:
    """
    The distinction the public surface does *not* follow, pinned so nobody "fixes" it later.

    A 404 here would make a misconfigured role look like a typo in the URL, and the route is already
    documented in the contract — hiding its existence hides nothing.
    """
    client = sign_in(Role.VIEWER)

    response = client.post(CATALOGUE_ROUTE, json={"name": "Ata"})

    assert response.status_code == 403
    assert response.json()["error_code"] == "PermissionDeniedException"


# ==========================================
# THE SESSION ITSELF
# ==========================================


def test_the_session_cookie_is_not_readable_by_scripts(client: TestClient) -> None:
    """
    The cookie attributes are part of the security model, so they are asserted and not assumed.

    ``Secure`` is deliberately **not** asserted: it is configuration (``AUTH_COOKIE_SECURE``) because
    over plain HTTP on a LAN the browser drops a ``Secure`` cookie silently and the login would look
    like it worked while nothing was stored.
    """
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@teste.local", "password": "senha de teste bem longa"},
    )

    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie.lower() or "samesite=lax" in cookie.lower()


def test_deactivating_an_account_takes_its_session_away_at_once(client: TestClient, auth_service, sign_in) -> None:
    """
    The end-to-end version of the rule the service enforces: the cookie stops working immediately,
    without waiting for it to expire and without a second login attempt.
    """
    client = sign_in(Role.CURATOR, email="curador@teste.local")
    assert client.get(READ_ROUTE).status_code == 200

    user = auth_service.users.get_by_email("curador@teste.local")
    assert user is not None
    auth_service.update_user(user, UpdateUserCommand(is_active=False))

    assert client.get(READ_ROUTE).status_code == 401


@pytest.mark.parametrize("role", list(Role))
def test_every_role_can_read_the_collection(sign_in, role: Role) -> None:
    """Reading is what an authenticated session *is*; there is no role that cannot read."""
    client = sign_in(role, email=f"{role.value.lower()}@teste.local")

    assert client.get(READ_ROUTE).status_code == 200
