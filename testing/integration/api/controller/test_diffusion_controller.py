"""HTTP contract of the diffusion channel surface: the registry, the lifecycle and the public site.

The service is the unit under test in ``testing/integration/diffusion/test_channel_service.py``; here
the envelope and the permissions are pinned. The route-access gate already walks the built app, so a
missing ``opt={"access": ...}`` fails there; these tests prove the levels in the two directions that
matter: an anonymous client cannot read the panel, and a curator cannot operate it.
"""

from litestar.testing import TestClient

from scrinalia.domains.identity.domain.permissions import Role


def test_the_channel_list_is_the_registry_with_the_configured_flag(client: TestClient) -> None:
    response = client.get("/api/v1/diffusion/channels")

    assert response.status_code == 200
    body = response.json()
    assert [channel["code"] for channel in body["channels"]] == ["public_site"]
    public_site = body["channels"][0]
    assert public_site["configured"] is False
    assert public_site["enabled"] is False
    assert public_site["capability"] == "LIVE"
    assert {field["name"] for field in public_site["config_fields"]} >= {"site_title", "locale", "allow_indexing"}


def test_the_patch_creates_the_row_and_the_pause_keeps_it(client: TestClient) -> None:
    created = client.patch(
        "/api/v1/diffusion/channels/public_site",
        json={"config": {"site_title": "Acervo"}},
    )

    assert created.status_code == 200
    body = created.json()
    assert body["configured"] is True
    assert body["enabled"] is True
    assert body["config"]["site_title"] == "Acervo"

    paused = client.patch("/api/v1/diffusion/channels/public_site", json={"enabled": False})

    assert paused.status_code == 200
    assert paused.json()["enabled"] is False
    assert paused.json()["config"]["site_title"] == "Acervo"


def test_the_public_site_is_404_before_the_channel_exists_and_200_after(client: TestClient) -> None:
    before = client.get("/api/v1/public/site")
    assert before.status_code == 404
    assert before.json()["error_code"] == "PublicSiteNotConfiguredError"

    client.patch("/api/v1/diffusion/channels/public_site", json={"config": {"site_title": "Acervo"}})

    after = client.get("/api/v1/public/site")
    assert after.status_code == 200
    assert after.json()["site_title"] == "Acervo"


def test_an_invalid_configuration_answers_422(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/diffusion/channels/public_site",
        json={"config": {"site_title": "Acervo", "contact_email": "nao-e-um-email"}},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "InvalidDiffusionConfigError"


def test_a_live_channel_refuses_a_schedule(client: TestClient) -> None:
    put = client.put("/api/v1/diffusion/channels/public_site/schedule", json={"cron": "0 2 * * *"})
    delete = client.delete("/api/v1/diffusion/channels/public_site/schedule")

    assert put.status_code == 422
    assert delete.status_code == 422


def test_an_unknown_channel_answers_404(client: TestClient) -> None:
    response = client.get("/api/v1/diffusion/channels/nope")

    assert response.status_code == 404
    assert response.json()["error_code"] == "DiffusionChannelNotFoundError"


def test_the_reads_are_authenticated_and_the_writes_are_operate(api_client: TestClient, sign_in) -> None:
    assert api_client.get("/api/v1/diffusion/channels").status_code == 401
    # The public identity is open even before the channel exists: it answers 404, not 401.
    assert api_client.get("/api/v1/public/site").status_code == 404

    curator = sign_in(Role.CURATOR)

    assert curator.get("/api/v1/diffusion/channels").status_code == 200
    refused = curator.patch("/api/v1/diffusion/channels/public_site", json={"enabled": False})
    assert refused.status_code == 403
