"""The cross-origin check on mutations, at the boundary a browser actually hits.

The decision itself is pinned as a pure function in ``testing/unit/api/test_origin_guard.py``. What
only HTTP can get wrong is *where* the guard sits: it must run on mutations and not on reads, before
the session is resolved, and it must not touch a request that carries no ``Origin`` at all — which is
every non-browser client, the test client included.
"""

from litestar.testing import TestClient

from scrinalia.core.config import settings

EMAIL = "maria@teste.local"
PASSWORD = "uma senha bem longa"


def _login(client: TestClient, *, origin: str | None = None):
    headers = {"Origin": origin} if origin else None
    return client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers=headers,
    )


def test_a_cross_origin_mutation_is_refused(api_client: TestClient) -> None:
    response = _login(api_client, origin="https://evil.example")

    assert response.status_code == 403
    assert response.json()["error_code"] == "PermissionDeniedException"


def test_the_origin_is_checked_before_the_session(api_client: TestClient) -> None:
    """
    A cross-origin mutation is refused as cross-origin, not as anonymous.

    The order matters for the log and for the answer: 401 would say "sign in" to a request that must
    never be made at all, and the origin guard is the cheapest of the two — it reads two headers and
    touches no database.
    """
    response = api_client.post(
        "/api/v1/taxonomy/tags/merge",
        json={},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403


def test_a_same_origin_mutation_is_allowed(api_client: TestClient, generate_user) -> None:
    """The SPA is same-origin in production; the test client is addressed as ``testserver.local``."""
    generate_user(email=EMAIL, password=PASSWORD)

    response = _login(api_client, origin="http://testserver.local")

    assert response.status_code == 200


def test_a_request_without_an_origin_is_allowed(api_client: TestClient, generate_user) -> None:
    """curl, the CLI and the test client send no ``Origin``; refusing them would defend nobody."""
    generate_user(email=EMAIL, password=PASSWORD)

    assert _login(api_client).status_code == 200


def test_a_read_is_not_checked(api_client: TestClient) -> None:
    """``GET`` changes nothing, and the diffusion surface is open by design."""
    response = api_client.get("/api/v1/public/documents", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200


def test_a_configured_origin_is_allowed_when_the_host_differs(
    api_client: TestClient, generate_user, monkeypatch
) -> None:
    """The reverse-proxy case the setting exists for: the public origin is not the internal Host."""
    monkeypatch.setattr(settings, "AUTH_TRUSTED_ORIGINS", "https://curador.arquivo.org")
    generate_user(email=EMAIL, password=PASSWORD)

    assert _login(api_client, origin="https://curador.arquivo.org").status_code == 200
