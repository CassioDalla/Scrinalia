"""
HTTP contract of the tag x entity collision.

The wiring and the status codes are asserted with the service mocked; the end-to-end path runs
through the real service and the real ledger, because the promise that matters here — "the number
the preview shows is the number the write produces, and the write can be reversed" — is only
meaningful through the router that writes.
"""

from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_ENTITY,
)
from litestar.testing import TestClient

from scrinalia.domains.archive.exceptions import (
    ConflictResolutionAlreadyUndoneError,
    ConflictResolutionNotFoundError,
    UnresolvableConflictError,
)
from scrinalia.domains.archive.schemas.entity_schema import (
    ConflictResolutionData,
    ConflictResolutionLogEntry,
    ConflictResolutionPlan,
    CrossDomainConflict,
    CrossDomainConflictPage,
    JudgedConflict,
    JudgedConflictPage,
)
from scrinalia.domains.archive.services.entity_service import EntityService


def _conflict(tag_id: int = 1, similarity: float = 0.97) -> CrossDomainConflict:
    return CrossDomainConflict(
        tag_id=tag_id,
        tag_name="rua visc. visconde de guarapuava",
        entity_id=2,
        entity_name="Rua Visconde De Guarapuava",
        entity_type="LOC",
        similarity=similarity,
    )


class TestConflictRoutes:
    def test_the_live_page_carries_the_totals_the_screen_cannot_derive(self, client: TestClient, mocker):
        mocker.patch.object(
            EntityService,
            "page_cross_domain_conflicts",
            return_value=CrossDomainConflictPage(
                total=2,
                limit=50,
                offset=0,
                items=[_conflict()],
                exact_name_count=5050,
                near_duplicate_count=122,
                judged_count=4,
            ),
        )

        response = client.get("/api/v1/taxonomy/conflicts/cross-domain")

        assert response.status_code == HTTP_200_OK
        body = response.json()
        assert body["exact_name_count"] == 5050
        assert body["near_duplicate_count"] == 122
        assert body["judged_count"] == 4
        # ``pair_kind`` is derived in the DTO, and the front reads it from the payload.
        assert body["items"][0]["pair_kind"] == "NEAR_DUPLICATE"

    def test_the_scope_reaches_the_service(self, client: TestClient, mocker):
        mocked = mocker.patch.object(
            EntityService,
            "page_cross_domain_conflicts",
            return_value=CrossDomainConflictPage(total=0, limit=10, offset=20),
        )

        client.get("/api/v1/taxonomy/conflicts/cross-domain?threshold=0.9&pair_kind=near_duplicate&limit=10&offset=20")

        mocked.assert_called_once_with(threshold=0.9, pair_kind="near_duplicate", limit=10, offset=20)

    def test_an_unknown_scope_is_refused(self, client: TestClient):
        response = client.get("/api/v1/taxonomy/conflicts/cross-domain?pair_kind=whatever")
        assert response.status_code in (HTTP_400_BAD_REQUEST, HTTP_422_UNPROCESSABLE_ENTITY)

    def test_the_judged_page_exposes_the_applicable_flag(self, client: TestClient, mocker):
        mocker.patch.object(
            EntityService,
            "list_judged_conflicts",
            return_value=JudgedConflictPage(
                total=1,
                limit=50,
                offset=0,
                items=[
                    JudgedConflict(
                        queue_id=9,
                        tag_id=1,
                        tag_name="pesquisa",
                        entity_id=2,
                        entity_name="Pesquisa",
                        entity_type="PER",
                        judge_winner="TAG",
                        judge_status="NEEDS_REVIEW",
                        tag_alive=True,
                        entity_alive=True,
                    )
                ],
                auto_resolved=65,
                sent_to_human=4,
                tag_wins=19,
                entity_wins=65,
                still_applicable=1,
            ),
        )

        body = client.get("/api/v1/taxonomy/conflicts/judged").json()

        assert body["auto_resolved"] == 65
        assert body["sent_to_human"] == 4
        # Derived in the DTO so the screen and the counter cannot disagree on "pending".
        assert body["items"][0]["applicable"] is True

    def test_the_preview_answers_both_verdicts(self, client: TestClient, mocker):
        mocked = mocker.patch.object(
            EntityService,
            "plan_conflict_resolution",
            return_value=ConflictResolutionPlan(
                tag_id=1,
                tag_name="batel",
                tag_document_count=4,
                entity_id=2,
                entity_name="Batel",
                entity_type="LOC",
                entity_document_count=7,
                tag_wins_documents_transferred=5,
                tag_wins_documents_already_linked=2,
                entity_wins_documents_transferred=2,
                entity_wins_documents_already_linked=2,
            ),
        )

        response = client.post("/api/v1/taxonomy/conflicts/resolve/preview", json={"tag_id": 1, "entity_id": 2})

        assert response.status_code == HTTP_200_OK
        body = response.json()
        assert body["tag_wins_documents_transferred"] == 5
        assert body["entity_wins_documents_transferred"] == 2
        assert mocked.call_args.args == (1, 2)

    def test_the_preview_refuses_an_unknown_field(self, client: TestClient):
        response = client.post(
            "/api/v1/taxonomy/conflicts/resolve/preview",
            json={"tag_id": 1, "entity_id": 2, "winner": "TAG"},
        )
        assert response.status_code in (HTTP_400_BAD_REQUEST, HTTP_422_UNPROCESSABLE_ENTITY)

    def test_the_resolution_returns_the_id_the_undo_needs(self, client: TestClient, mocker):
        mocked = mocker.patch.object(
            EntityService,
            "resolve_cross_domain_conflict",
            return_value=ConflictResolutionData(
                winner="TAG", documents_transferred=5, resolution_id=42, ban_kind="NER_EXCLUSION", ban_term="Batel"
            ),
        )

        response = client.post(
            "/api/v1/taxonomy/conflicts/resolve",
            json={"winner": "TAG", "tag_id": 1, "entity_id": 2, "decided_by": "ana", "note": "bairro é local"},
        )

        assert response.status_code == HTTP_201_CREATED
        body = response.json()
        assert body["data"]["resolution_id"] == 42
        command = mocked.call_args.args[0]
        assert command.decided_by == "ana"
        assert command.note == "bairro é local"

    def test_an_unresolvable_pair_is_422(self, client: TestClient, mocker):
        mocker.patch.object(
            EntityService,
            "resolve_cross_domain_conflict",
            side_effect=UnresolvableConflictError("A entidade deste par não existe mais."),
        )
        response = client.post(
            "/api/v1/taxonomy/conflicts/resolve", json={"winner": "TAG", "tag_id": 1, "entity_id": 2}
        )
        assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY

    def test_undoing_twice_is_409_and_an_unknown_id_is_404(self, client: TestClient, mocker):
        mocked = mocker.patch.object(EntityService, "undo_conflict_resolution")
        mocked.side_effect = ConflictResolutionAlreadyUndoneError("já foi desfeita")
        assert client.delete("/api/v1/taxonomy/conflicts/resolutions/7").status_code == HTTP_409_CONFLICT

        mocked.side_effect = ConflictResolutionNotFoundError("não existe")
        assert client.delete("/api/v1/taxonomy/conflicts/resolutions/999").status_code == HTTP_404_NOT_FOUND

    def test_the_ledger_lists_the_written_rows(self, client: TestClient, mocker):
        mocker.patch.object(
            EntityService,
            "list_conflict_resolutions",
            return_value=(
                [
                    ConflictResolutionLogEntry(
                        resolution_id=3,
                        winner="ENTITY",
                        source="JUDGE",
                        tag_id=1,
                        tag_name="batel",
                        entity_id=2,
                        entity_name="Batel",
                        entity_type="LOC",
                        documents_transferred=4,
                        ban_kind="STOPWORD",
                        ban_term="batel",
                        ban_created=True,
                    )
                ],
                1,
            ),
        )

        body = client.get("/api/v1/taxonomy/conflicts/resolutions").json()

        assert body["total"] == 1
        assert body["items"][0]["is_undone"] is False
        assert body["items"][0]["ban_kind"] == "STOPWORD"


class TestConflictLifecycle:
    """The whole cycle over HTTP, with the real service and the real ledger."""

    def test_preview_then_resolve_then_undo(
        self, client: TestClient, api_uses_test_db, db_session, generate_archive_doc
    ):
        """
        The number the preview shows is the number the write produces, and the undo puts it back.

        This is the promise the route could not make before: ``POST /conflicts/resolve`` transferred
        the documents and deleted the losing row with no dry run and no way back.
        """
        from scrinalia.domains.archive.models import (
            ArchiveDocumentEntity,
            ArchiveDocumentTag,
            ArchiveEntity,
            ArchiveTag,
        )

        tag = ArchiveTag(name="batel")
        entity = ArchiveEntity(name="Batel", entity_type="LOC")
        db_session.add_all([tag, entity])
        db_session.flush()

        first = generate_archive_doc(original_title="Já tinha a tag")
        second = generate_archive_doc(original_title="Só a entidade")
        db_session.add_all(
            [
                ArchiveDocumentTag(description_id=first.description_id, tag_id=tag.tag_id),
                ArchiveDocumentEntity(description_id=first.description_id, entity_id=entity.entity_id),
                ArchiveDocumentEntity(description_id=second.description_id, entity_id=entity.entity_id),
            ]
        )
        db_session.flush()

        preview = client.post(
            "/api/v1/taxonomy/conflicts/resolve/preview",
            json={"tag_id": tag.tag_id, "entity_id": entity.entity_id},
        )
        assert preview.status_code == HTTP_200_OK
        plan = preview.json()
        assert plan["tag_alive"] is True and plan["entity_alive"] is True
        assert plan["resolvable"] is True
        # TAG wins: one new link, one that already existed.
        assert plan["tag_wins_documents_transferred"] == 1
        assert plan["tag_wins_documents_already_linked"] == 1

        resolved = client.post(
            "/api/v1/taxonomy/conflicts/resolve",
            json={
                "winner": "TAG",
                "tag_id": tag.tag_id,
                "entity_id": entity.entity_id,
                "decided_by": "ana",
                "note": "bairro é local, não assunto",
            },
        )
        assert resolved.status_code == HTTP_201_CREATED
        data = resolved.json()["data"]
        assert data["documents_transferred"] == plan["tag_wins_documents_transferred"]
        assert data["ban_kind"] == "NER_EXCLUSION"

        # The write is in the ledger, and the entity is gone.
        ledger = client.get("/api/v1/taxonomy/conflicts/resolutions").json()
        assert ledger["total"] == 1
        assert ledger["items"][0]["resolution_id"] == data["resolution_id"]
        assert ledger["items"][0]["decided_by"] == "ana"
        assert db_session.get(ArchiveEntity, entity.entity_id) is None

        undone = client.delete(f"/api/v1/taxonomy/conflicts/resolutions/{data['resolution_id']}?undone_by=bruno")
        assert undone.status_code == HTTP_200_OK
        assert undone.json()["data"]["loser_restored"] is True

        # The row is back with its id, and the ledger keeps the history.
        restored = db_session.get(ArchiveEntity, entity.entity_id)
        assert restored is not None and restored.name == "Batel"
        ledger = client.get("/api/v1/taxonomy/conflicts/resolutions").json()
        assert ledger["items"][0]["is_undone"] is True
        assert ledger["items"][0]["undone_by"] == "bruno"

    def test_an_unknown_pair_is_refused_with_422(self, client: TestClient, api_uses_test_db, db_session):
        """A pair whose sides do not exist cannot be resolved, and the message says which side."""
        response = client.post(
            "/api/v1/taxonomy/conflicts/resolve", json={"winner": "TAG", "tag_id": 999001, "entity_id": 999002}
        )
        assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY
        assert "existe" in response.json()["message"]
