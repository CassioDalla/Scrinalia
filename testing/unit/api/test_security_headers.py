"""The response-header policy: one set, applied to every answer of the application.

The property is not "the header exists somewhere" but "the same policy reaches a JSON answer, an
HTML answer, a refusal produced outside the handler layer, and the static files of the SPA". The
OpenAPI pages are the one documented exception, because Litestar's render plugins load their assets
from CDNs and then run an inline initialiser.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from litestar import Litestar, Response, get
from litestar.testing import TestClient

from scrinalia.api.security_headers import (
    CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
)
from scrinalia.asgi import create_app
from scrinalia.core.config import settings


@get("/json")
async def _json() -> dict[str, bool]:
    return {"ok": True}


@get("/html")
async def _html() -> Response[str]:
    return Response(content="<html><body>ok</body></html>", media_type="text/html")


@pytest.fixture
def security_client() -> Iterator[TestClient]:
    """An app whose only middleware is the policy, so the assertions read one decision."""
    with TestClient(app=Litestar(route_handlers=[_json, _html], middleware=[SecurityHeadersMiddleware()])) as client:
        yield client


def _assert_policy(headers: Mapping[str, str], *, csp: bool) -> None:
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-frame-options"] == "DENY"
    if csp:
        assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    else:
        assert "content-security-policy" not in headers


def test_a_json_answer_and_an_html_answer_carry_the_same_header_set(security_client: TestClient) -> None:
    """The media type does not select a policy: one set, two shapes."""
    json_response = security_client.get("/json")
    html_response = security_client.get("/html")

    _assert_policy(json_response.headers, csp=True)
    _assert_policy(html_response.headers, csp=True)
    assert json_response.headers["content-security-policy"] == html_response.headers["content-security-policy"]


def test_the_csp_allows_the_spa_bundle_and_its_computed_styles() -> None:
    """
    The two allowances are measured facts, not defaults.

    ``script-src 'self'`` is the whole script policy: the built entry is an external module script
    and there is no inline script. ``style-src`` has to accept ``'unsafe-inline'`` because six
    screens compute a dynamic ``style={{...}}``, which a nonce cannot cover.
    """
    assert "script-src 'self'" in CONTENT_SECURITY_POLICY
    assert "style-src 'self' 'unsafe-inline'" in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    assert "object-src 'none'" in CONTENT_SECURITY_POLICY
    assert "unsafe-eval" not in CONTENT_SECURITY_POLICY


def test_hsts_is_absent_until_the_deployment_declares_https(
    security_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A LAN installation over HTTP must not claim HTTPS; the operator opts in with the setting."""
    monkeypatch.setattr(settings, "SECURITY_HSTS_SECONDS", 0)
    assert "strict-transport-security" not in security_client.get("/json").headers

    monkeypatch.setattr(settings, "SECURITY_HSTS_SECONDS", 31_536_000)
    hsts = security_client.get("/json").headers["strict-transport-security"]

    assert hsts == "max-age=31536000"
    assert "includeSubDomains" not in hsts


def test_the_openapi_pages_are_exempt_from_the_csp(security_client: TestClient) -> None:
    """Swagger/Redoc/RapiDoc/Stoplight load from CDNs and run an inline initialiser."""
    swagger = security_client.get("/schema/swagger")
    document = security_client.get("/schema/openapi.json")

    assert swagger.status_code == 200
    _assert_policy(swagger.headers, csp=False)
    _assert_policy(document.headers, csp=False)


def test_the_real_app_applies_the_policy_to_a_json_answer() -> None:
    """The middleware is registered in ``create_app``, not only available to a test app."""
    with TestClient(app=create_app()) as client:
        _assert_policy(client.get("/health/live").headers, csp=True)


def test_the_spa_index_and_a_deep_link_carry_the_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The static router and its client-side-routing fallback are route types of their own.

    The build is staged in a temporary directory so the test does not depend on
    ``apps/curator/dist`` existing — the pytest job runs before the front-end job in CI.
    """
    (tmp_path / "index.html").write_text("<!doctype html><html><body>spa</body></html>", encoding="utf-8")
    monkeypatch.setattr("scrinalia.api.spa.DIST_DIRECTORY", tmp_path)

    with TestClient(app=create_app()) as client:
        for path in ("/", "/acervo/lista"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")
            _assert_policy(response.headers, csp=True)
