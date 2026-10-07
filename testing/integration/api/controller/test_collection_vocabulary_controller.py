"""
HTTP contract of the collection vocabulary catalogue.

The wiring is asserted with the service mocked; the promise that matters is asserted end to end
with the real repository, because "a term the archivist registers is a term the subject guard
refuses" only means anything through the database the guard actually reads.
"""

from litestar.status_codes import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_ENTITY,
)
from litestar.testing import TestClient

from scrinalia.domains.archive.exceptions import (
    ArrangementTermNotFoundError,
    DuplicateArrangementTermError,
    DuplicateCollectionTermError,
)
from scrinalia.domains.archive.schemas.collection_vocabulary_schema import (
    ArrangementTermDTO,
    CollectionTermDTO,
    CollectionVocabularyResponse,
)
from scrinalia.domains.archive.services.collection_vocabulary_service import CollectionVocabularyService


def _response() -> CollectionVocabularyResponse:
    return CollectionVocabularyResponse(
        arrangement_terms=[ArrangementTermDTO(term_id=1, token="SMU", display_name="SMU - Urbanismo", is_active=True)],
        collection_terms=[CollectionTermDTO(term_id=2, term="centro", kind="DISTRICT", is_active=True, tag_count=4)],
        kinds=["DISTRICT", "MUNICIPALITY", "STATE", "REGION", "COUNTRY", "PERSON"],
    )


class TestVocabularyRoutes:
    def test_both_catalogues_come_back_together(self, client: TestClient, mocker):
        mocker.patch.object(CollectionVocabularyService, "read", return_value=_response())
        body = client.get("/api/v1/vocabulary").json()
        assert body["arrangement_terms"][0]["token"] == "SMU"
        assert body["collection_terms"][0]["tag_count"] == 4
        # The kinds travel with the read so the screen renders the select from the definition.
        assert "PERSON" in body["kinds"]

    def test_a_created_arrangement_term_answers_201(self, client: TestClient, mocker):
        mocked = mocker.patch.object(
            CollectionVocabularyService,
            "create_arrangement_term",
            return_value=ArrangementTermDTO(term_id=9, token="ED", display_name="Edificações", is_active=True),
        )
        response = client.post(
            "/api/v1/vocabulary/arrangement-terms", json={"token": "ED", "display_name": "Edificações"}
        )
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["term_id"] == 9
        assert mocked.call_args.args[0].token == "ED"

    def test_a_taken_token_is_409(self, client: TestClient, mocker):
        mocker.patch.object(
            CollectionVocabularyService,
            "create_arrangement_term",
            side_effect=DuplicateArrangementTermError("já existe"),
        )
        response = client.post("/api/v1/vocabulary/arrangement-terms", json={"token": "ED", "display_name": "Outro"})
        assert response.status_code == HTTP_409_CONFLICT
        assert response.json()["error_code"] == "DuplicateArrangementTermError"

    def test_renaming_a_missing_term_is_404(self, client: TestClient, mocker):
        mocker.patch.object(
            CollectionVocabularyService,
            "update_arrangement_term",
            side_effect=ArrangementTermNotFoundError("não existe"),
        )
        assert (
            client.patch("/api/v1/vocabulary/arrangement-terms/999", json={"is_active": False}).status_code
            == HTTP_404_NOT_FOUND
        )

    def test_a_duplicate_collection_term_is_409(self, client: TestClient, mocker):
        mocker.patch.object(
            CollectionVocabularyService, "create_collection_term", side_effect=DuplicateCollectionTermError("já existe")
        )
        response = client.post("/api/v1/vocabulary/collection-terms", json={"term": "centro", "kind": "DISTRICT"})
        assert response.status_code == HTTP_409_CONFLICT
        assert response.json()["error_code"] == "DuplicateCollectionTermError"

    def test_there_is_no_delete(self, client: TestClient):
        """Retiring is ``is_active=false``; a delete would make a refused term come back."""
        assert client.delete("/api/v1/vocabulary/arrangement-terms/1").status_code == 405
        assert client.delete("/api/v1/vocabulary/collection-terms/1").status_code == 405

    def test_an_unknown_kind_is_refused(self, client: TestClient):
        response = client.post("/api/v1/vocabulary/collection-terms", json={"term": "x", "kind": "PLANET"})
        assert response.status_code in (HTTP_400_BAD_REQUEST, HTTP_422_UNPROCESSABLE_ENTITY)


class TestTheCatalogueReachesTheGuard:
    """End to end: the row the archivist writes is the row the subject guard reads."""

    def test_a_registered_person_name_stops_being_a_subject(
        self, client: TestClient, api_uses_test_db, db_session, generate_archive_doc
    ):
        from scrinalia.domains.archive.models import ArchiveTag

        generate_archive_doc(description_id="s1", original_title="A")
        db_session.add(ArchiveTag(name="jaime lerner"))
        db_session.flush()

        # Before the catalogue declares the name, the guard has no reason to refuse it.
        before = client.get("/api/v1/taxonomy/tags/subject-exclusions/suggestions").json()
        assert "jaime lerner" not in [item["term"] for item in before["items"]]

        created = client.post("/api/v1/vocabulary/collection-terms", json={"term": "Jaime Lerner", "kind": "PERSON"})
        assert created.status_code == HTTP_201_CREATED
        # Stored normalised: the guard matches on the lowercase form.
        assert created.json()["term"] == "jaime lerner"

        after = client.get("/api/v1/taxonomy/tags/subject-exclusions/suggestions").json()
        by_term = {item["term"]: item for item in after["items"]}
        assert by_term["jaime lerner"]["signal"] == "PERSON"

    def test_retiring_a_term_takes_it_back_out_of_the_guard(
        self, client: TestClient, api_uses_test_db, db_session, generate_archive_doc
    ):
        from scrinalia.domains.archive.models import ArchiveTag

        generate_archive_doc(description_id="s2", original_title="A")
        db_session.add(ArchiveTag(name="centro"))
        db_session.flush()

        term_id = client.post(
            "/api/v1/vocabulary/collection-terms", json={"term": "centro", "kind": "DISTRICT"}
        ).json()["term_id"]
        assert (
            client.patch(f"/api/v1/vocabulary/collection-terms/{term_id}", json={"is_active": False}).status_code == 200
        )

        # Retired, not deleted: the row stays in the catalogue and leaves the guard's reach.
        listed = client.get("/api/v1/vocabulary").json()["collection_terms"]
        assert [(row["term"], row["is_active"]) for row in listed] == [("centro", False)]
        after = client.get("/api/v1/taxonomy/tags/subject-exclusions/suggestions").json()
        assert "centro" not in [item["term"] for item in after["items"]]
