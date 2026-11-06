"""The public surface's brake over HTTP: who is counted, what a refusal says, where the limit stops.

The unit tests pin the window; this file pins that the window is wired to ``/api/v1/public/*`` and
that its refusal is still the API's answer — a ``RouteMessageCode``, a sentence in the request's
language, ``Retry-After`` and the request's correlation id — instead of a bare 429 from nowhere.
"""

from __future__ import annotations

import pytest
from litestar.testing import TestClient

from scrinalia.api.controllers.public_controller import PublicController
from scrinalia.api.public_rate_limit import PUBLIC_API_PREFIX
from scrinalia.core.config import settings


@pytest.fixture(autouse=True)
def tight_public_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two requests per minute: the smallest window that still has a second request to allow."""
    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT_MAX", 2)
    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT_WINDOW_SECONDS", 60)


def test_the_ceiling_refuses_with_a_code_a_retry_after_and_the_request_id(api_client: TestClient) -> None:
    """
    The first two requests reach the handler (404: no public_site channel configured) and count;
    the third is refused before the handler runs, and the refusal is the API's shape.
    """
    assert api_client.get("/api/v1/public/site").status_code == 404
    assert api_client.get("/api/v1/public/site").status_code == 404

    response = api_client.get("/api/v1/public/site", headers={"Accept-Language": "en"})

    assert response.status_code == 429
    assert response.json() == {
        "error_code": "PublicRateLimited",
        "code": "PUBLIC_RATE_LIMITED",
        "message": "Too many requests from this address. Wait a moment.",
    }
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert response.headers["x-request-id"]
    assert "content-security-policy" in response.headers


def test_the_refusal_speaks_the_product_language_by_default(api_client: TestClient) -> None:
    """A client that sends no ``Accept-Language`` keeps receiving Portuguese, as everywhere else."""
    api_client.get("/api/v1/public/site")
    api_client.get("/api/v1/public/site")

    response = api_client.get("/api/v1/public/site")

    assert response.status_code == 429
    assert response.json()["message"] == "Muitas requisições deste endereço. Aguarde alguns instantes."


def test_the_brake_covers_the_public_prefix_and_not_the_rest(api_client: TestClient) -> None:
    """The curator surface and the orchestrator's probes are not paid for by a public visitor."""
    assert api_client.get("/api/v1/public/site").status_code == 404
    assert api_client.get("/api/v1/public/site").status_code == 404
    assert api_client.get("/api/v1/public/site").status_code == 429

    assert api_client.get("/health/live").status_code == 200
    assert api_client.get("/api/v1/documents").status_code == 401


def test_the_prefix_is_the_public_controllers_own_path() -> None:
    """
    One definition, pinned: a rename of ``PublicController.path`` that left the middleware's
    constant behind would silently remove the limit, and no other test would notice.
    """
    assert PublicController.path == PUBLIC_API_PREFIX
