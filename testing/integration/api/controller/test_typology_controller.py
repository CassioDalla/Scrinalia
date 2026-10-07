"""
HTTP contract of the typology catalogue.

Two layers, like the hierarchy controller's tests: the **wiring and status codes** with the service
mocked, so the surface is asserted without a database, and one **end-to-end path** with the real
service and the real database, because the promise that matters — "retiring a typology takes it out
of the classifier's candidate labels without unclassifying a single description" — is only
meaningful through the repository that would have done it.
"""

import pytest
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_ENTITY,
)
from litestar.testing import TestClient

from scrinalia.asgi import create_app
from scrinalia.domains.archive.exceptions import (
    DuplicateTypologyError,
    TypologyNotFoundError,
)
from scrinalia.domains.archive.schemas.typology_schema import TypologyDTO
from scrinalia.domains.archive.services.typology_service import TypologyService


@pytest.fixture
def client() -> TestClient:  # type: ignore
    with TestClient(app=create_app()) as test_client:
        yield test_client  # type: ignore


def _typology(typology_id: int = 7, name: str = "Ata de Reunião", is_active: bool = True) -> TypologyDTO:
    return TypologyDTO(
        typology_id=typology_id,
        name=name,
        context_description="Registros de encontros e deliberações.",
        is_active=is_active,
        document_count=3,
    )


class TestTypologyRoutes:
    def test_the_catalogue_is_listed(self, client: TestClient, mocker):
        mocker.patch.object(TypologyService, "list_typologies", return_value=[_typology()])
        response = client.get("/api/v1/typologies")
        assert response.status_code == HTTP_200_OK
        assert response.json()[0]["name"] == "Ata de Reunião"
        assert response.json()[0]["document_count"] == 3

    def test_only_active_reaches_the_service(self, client: TestClient, mocker):
        mocked = mocker.patch.object(TypologyService, "list_typologies", return_value=[])
        client.get("/api/v1/typologies?only_active=true")
        mocked.assert_called_once_with(only_active=True)

    def test_a_created_typology_answers_201(self, client: TestClient, mocker):
        mocked = mocker.patch.object(TypologyService, "create_typology", return_value=_typology())
        response = client.post("/api/v1/typologies", json={"name": "Ata de Reunião"})
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["typology_id"] == 7
        assert mocked.call_args.args[0].name == "Ata de Reunião"

    def test_a_taken_name_is_409(self, client: TestClient, mocker):
        mocker.patch.object(TypologyService, "create_typology", side_effect=DuplicateTypologyError("já existe"))
        response = client.post("/api/v1/typologies", json={"name": "Fotografia"})
        assert response.status_code == HTTP_409_CONFLICT
        assert response.json()["error_code"] == "DuplicateTypologyError"

    def test_renaming_a_missing_typology_is_404(self, client: TestClient, mocker):
        mocker.patch.object(TypologyService, "update_typology", side_effect=TypologyNotFoundError("não existe"))
        assert client.patch("/api/v1/typologies/999", json={"name": "Outra"}).status_code == HTTP_404_NOT_FOUND

    def test_deactivating_is_a_patch_and_not_a_delete(self, client: TestClient, mocker):
        """
        There is no ``DELETE``: the FK is ``SET NULL``, so a removal would silently unclassify the
        descriptions carrying the typology. The route table itself has to say so.
        """
        mocked = mocker.patch.object(TypologyService, "update_typology", return_value=_typology(is_active=False))
        response = client.patch("/api/v1/typologies/7", json={"is_active": False})
        assert response.status_code == HTTP_200_OK
        assert response.json()["is_active"] is False
        assert mocked.call_args.args[1].is_active is False

        assert client.delete("/api/v1/typologies/7").status_code == 405

    def test_an_unknown_field_is_refused(self, client: TestClient):
        response = client.post("/api/v1/typologies", json={"name": "Ata", "typology_id": 4})
        assert response.status_code in (HTTP_400_BAD_REQUEST, HTTP_422_UNPROCESSABLE_ENTITY)

    def test_a_name_that_is_not_a_string_is_refused(self, client: TestClient):
        response = client.post("/api/v1/typologies", json={"name": 12})
        assert response.status_code in (HTTP_400_BAD_REQUEST, HTTP_422_UNPROCESSABLE_ENTITY)


class TestTypologyLifecycle:
    """The whole cycle over HTTP, with the real service and the real catalogue table."""

    def test_create_rename_and_retire(self, client: TestClient, api_uses_test_db, db_session):
        created = client.post(
            "/api/v1/typologies",
            json={"name": "Ata de Reunião", "context_description": "Encontros e deliberações."},
        )
        assert created.status_code == HTTP_201_CREATED
        typology_id = created.json()["typology_id"]
        assert created.json()["is_active"] is True
        assert created.json()["document_count"] == 0

        # A second one with the same spelling in another case is the same typology.
        duplicate = client.post("/api/v1/typologies", json={"name": "ata de reunião"})
        assert duplicate.status_code == HTTP_409_CONFLICT

        renamed = client.patch(f"/api/v1/typologies/{typology_id}", json={"name": "Ata"})
        assert renamed.status_code == HTTP_200_OK
        assert renamed.json()["name"] == "Ata"

        retired = client.patch(f"/api/v1/typologies/{typology_id}", json={"is_active": False})
        assert retired.status_code == HTTP_200_OK

        # Retired, not gone: the catalogue screen still has to weigh it.
        listed = client.get("/api/v1/typologies").json()
        assert [row["name"] for row in listed] == ["Ata"]
        assert listed[0]["is_active"] is False
        assert client.get("/api/v1/typologies?only_active=true").json() == []

    def test_the_archivist_can_assign_a_typology_to_one_description(
        self, client: TestClient, api_uses_test_db, db_session, generate_archive_doc
    ):
        """
        The gap this closes: the classifier was the only writer of ``typology_id``.

        The assignment goes through the same wide ``PATCH`` the other ISAD(G) fields do, so it is
        recorded in the revision ledger and the document becomes ``HUMAN_APPROVED``.
        """
        typology_id = client.post("/api/v1/typologies", json={"name": "Planta"}).json()["typology_id"]
        document = generate_archive_doc()

        response = client.patch(
            f"/api/v1/documents/{document.description_id}",
            json={"typology_id": typology_id, "changed_by": "ana", "review_note": "Planta conferida"},
        )

        assert response.status_code == HTTP_200_OK
        assert response.json()["typology_id"] == typology_id
        assert response.json()["typology"] == "Planta"

        revisions = client.get(f"/api/v1/documents/{document.description_id}/revisions").json()
        assert revisions[0]["changes"]["typology_id"]["new"] == typology_id

    def test_an_unknown_typology_is_refused_with_422(
        self, client: TestClient, api_uses_test_db, db_session, generate_archive_doc
    ):
        """
        A human choosing a typology makes a claim the catalogue has to answer.

        Storing ``NULL`` would turn a wrong id into missing data, so the write is refused instead of
        silently ignored — the same asymmetry the level catalogue has.
        """
        document = generate_archive_doc()

        response = client.patch(f"/api/v1/documents/{document.description_id}", json={"typology_id": 4242})

        assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY
        assert client.get(f"/api/v1/documents/{document.description_id}").json()["typology_id"] is None
