"""HTTP contract of the publication gesture: the envelope, the permissions and the refusals.

The service is the unit under test in ``testing/integration/diffusion/test_publication_service.py``;
here the route's shape and its access level are pinned. The route-access gate already walks the built
app, so a missing ``opt={"access": ...}`` fails there; these tests prove the two directions that
matter: an anonymous client cannot read the queue, and a viewer can read it but cannot publish.
"""

from datetime import UTC, datetime, timedelta

from litestar.testing import TestClient
from pytest_mock import MockerFixture

from scrinalia.domains.diffusion.exceptions import (
    PublicationBatchNotFoundError,
    PublicationPreviewStaleError,
    PublicationRefusedError,
)
from scrinalia.domains.diffusion.publication_schemas import (
    PublicationAction,
    PublicationBatchDTO,
    PublicationBatchListDTO,
    PublicationChannelPreviewDTO,
    PublicationPreviewDTO,
    PublicationSkippedDTO,
    PublicationUndoDTO,
)
from scrinalia.domains.diffusion.publication_service import DiffusionPublicationService
from scrinalia.domains.identity.domain.permissions import Role


def _preview() -> PublicationPreviewDTO:
    return PublicationPreviewDTO(
        token="1700000000.abc",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
        channels=[
            PublicationChannelPreviewDTO(
                code="public_site",
                label="Site público",
                eligible=3,
                sample=[],
                skipped=PublicationSkippedDTO(not_approved=1),
            )
        ],
        total_eligible=3,
    )


def test_the_reads_are_authenticated_and_the_writes_are_curate(api_client: TestClient, sign_in) -> None:
    assert api_client.get("/api/v1/diffusion/publications").status_code == 401
    assert api_client.post("/api/v1/diffusion/publications/preview", json={}).status_code == 401

    viewer = sign_in(Role.VIEWER)
    assert viewer.get("/api/v1/diffusion/publications").status_code == 200
    assert viewer.get("/api/v1/diffusion/publications/summary").status_code == 200
    assert viewer.get("/api/v1/diffusion/scopes").status_code == 200
    refused = viewer.post(
        "/api/v1/diffusion/publications/preview",
        json={"action": "PUBLISH", "channel_codes": ["public_site"], "node_id": "fundo"},
    )
    assert refused.status_code == 403


def test_the_preview_answers_the_token_and_the_channels(client: TestClient, mocker: MockerFixture) -> None:
    mock = mocker.patch.object(DiffusionPublicationService, "preview")
    mock.return_value = _preview()

    response = client.post(
        "/api/v1/diffusion/publications/preview",
        json={"action": "PUBLISH", "channel_codes": ["public_site"], "node_id": "fundo"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token"] == "1700000000.abc"
    assert body["channels"][0]["eligible"] == 3
    assert body["total_eligible"] == 3


def test_the_apply_echoes_the_request_and_the_token(client: TestClient, mocker: MockerFixture) -> None:
    mock = mocker.patch.object(DiffusionPublicationService, "apply")
    mock.return_value = PublicationBatchDTO(
        batch_id=9,
        action=PublicationAction.PUBLISH,
        channels=["public_site"],
        applied_count=3,
        created_at=datetime.now(UTC),
    )

    response = client.post(
        "/api/v1/diffusion/publications",
        json={
            "request": {"action": "PUBLISH", "channel_codes": ["public_site"], "node_id": "fundo"},
            "token": "1700000000.abc",
        },
    )

    assert response.status_code == 201
    assert response.json()["batch_id"] == 9
    assert mock.call_args.kwargs["author"] is not None


def test_a_stale_token_answers_409(client: TestClient, mocker: MockerFixture) -> None:
    mocker.patch.object(
        DiffusionPublicationService,
        "apply",
        side_effect=PublicationPreviewStaleError("o conjunto mudou"),
    )

    response = client.post(
        "/api/v1/diffusion/publications",
        json={
            "request": {"action": "PUBLISH", "channel_codes": ["public_site"], "node_id": "fundo"},
            "token": "expirado",
        },
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "PublicationPreviewStaleError"


def test_nothing_to_do_answers_422(client: TestClient, mocker: MockerFixture) -> None:
    mocker.patch.object(
        DiffusionPublicationService,
        "apply",
        side_effect=PublicationRefusedError("nada a fazer"),
    )

    response = client.post(
        "/api/v1/diffusion/publications",
        json={
            "request": {"action": "PUBLISH", "channel_codes": ["public_site"], "node_id": "fundo"},
            "token": "x",
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "PublicationRefusedError"


def test_the_undo_of_a_missing_batch_answers_404(client: TestClient, mocker: MockerFixture) -> None:
    mocker.patch.object(
        DiffusionPublicationService,
        "undo",
        side_effect=PublicationBatchNotFoundError("lote não encontrado"),
    )

    response = client.post("/api/v1/diffusion/publications/batches/404/undo")

    assert response.status_code == 404
    assert response.json()["error_code"] == "PublicationBatchNotFoundError"


def test_the_history_answers_the_batches(client: TestClient, mocker: MockerFixture) -> None:
    mock = mocker.patch.object(DiffusionPublicationService, "history")
    mock.return_value = PublicationBatchListDTO(batches=[], generated_at=datetime.now(UTC))

    response = client.get("/api/v1/diffusion/publications/batches?limit=10")

    assert response.status_code == 200
    assert response.json()["batches"] == []
    assert mock.call_args.args == (10, 0)


def test_the_undo_answers_what_it_restored(client: TestClient, mocker: MockerFixture) -> None:
    mock = mocker.patch.object(DiffusionPublicationService, "undo")
    mock.return_value = PublicationUndoDTO(batch_id=7, restored=2, skipped=1, undone_at=datetime.now(UTC))

    response = client.post("/api/v1/diffusion/publications/batches/7/undo")

    assert response.status_code == 200
    assert response.json()["restored"] == 2
    assert response.json()["skipped"] == 1
