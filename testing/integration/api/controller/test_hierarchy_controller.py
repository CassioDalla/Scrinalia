"""
HTTP contract of the hierarchy controller.

Two layers are pinned here on purpose:

* the **wiring and the status codes**, with the services mocked, so the HTTP surface is asserted
  without a database; and
* one **end-to-end path** with the real service and the real database (`api_uses_test_db`), because the
  contract that matters most — "the proposal writes nothing" — is only meaningful through the
  router that could have written.
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

from memoria_curitibana.asgi import create_app
from memoria_curitibana.domains.archive.exceptions import (
    DescriptionLevelNotFoundError,
    DuplicateDescriptionLevelError,
    HierarchyNodeNotFoundError,
    InvalidHierarchyMoveError,
)
from memoria_curitibana.domains.archive.models import ArchiveDocument
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    DescriptionLevelDTO,
    HierarchyNodeSummary,
    HierarchyProposalResponse,
    HierarchyTreeResponse,
)
from memoria_curitibana.domains.archive.services.hierarchy_proposal_service import HierarchyProposalService
from memoria_curitibana.domains.archive.services.hierarchy_service import HierarchyService
from memoria_curitibana.domains.archive.services.level_catalog_service import LevelCatalogService


@pytest.fixture
def client() -> TestClient:  # type: ignore
    with TestClient(app=create_app()) as test_client:
        yield test_client  # type: ignore


def _level(level_id: int = 3, code: str = "serie", name: str = "Série") -> DescriptionLevelDTO:
    return DescriptionLevelDTO(
        level_id=level_id,
        ordinal=3,
        code=code,
        name=name,
        requires_parent=False,
        allows_children=True,
        is_active=True,
    )


def _node(description_id: str = "n1") -> HierarchyNodeSummary:
    return HierarchyNodeSummary(description_id=description_id, path=description_id)


class TestLevels:
    def test_the_ladder_is_listed(self, client: TestClient, mocker):
        mocker.patch.object(LevelCatalogService, "list_levels", return_value=[_level()])
        response = client.get("/api/v1/hierarchy/levels")
        assert response.status_code == HTTP_200_OK
        assert response.json()[0]["code"] == "serie"
        assert response.json()[0]["requires_parent"] is False

    def test_only_active_reaches_the_service(self, client: TestClient, mocker):
        mocked = mocker.patch.object(LevelCatalogService, "list_levels", return_value=[])
        client.get("/api/v1/hierarchy/levels?only_active=true")
        mocked.assert_called_once_with(only_active=True)

    def test_a_created_rung_answers_201(self, client: TestClient, mocker):
        mocker.patch.object(LevelCatalogService, "create_level", return_value=_level())
        response = client.post(
            "/api/v1/hierarchy/levels",
            json={"ordinal": 3, "code": "serie", "name": "Série"},
        )
        assert response.status_code == HTTP_201_CREATED

    def test_a_taken_rung_is_409(self, client: TestClient, mocker):
        mocker.patch.object(
            LevelCatalogService, "create_level", side_effect=DuplicateDescriptionLevelError("já existe")
        )
        response = client.post(
            "/api/v1/hierarchy/levels",
            json={"ordinal": 3, "code": "serie", "name": "Série"},
        )
        assert response.status_code == HTTP_409_CONFLICT
        assert response.json()["error_code"] == "DuplicateDescriptionLevelError"

    def test_an_unknown_field_is_refused(self, client: TestClient):
        response = client.post(
            "/api/v1/hierarchy/levels",
            json={"ordinal": 3, "code": "serie", "name": "Série", "level_id": 1},
        )
        assert response.status_code in (HTTP_400_BAD_REQUEST, HTTP_422_UNPROCESSABLE_ENTITY)

    def test_renaming_a_missing_rung_is_404(self, client: TestClient, mocker):
        mocker.patch.object(
            LevelCatalogService, "update_level", side_effect=DescriptionLevelNotFoundError("não existe")
        )
        assert client.patch("/api/v1/hierarchy/levels/999", json={"name": "Outra"}).status_code == HTTP_404_NOT_FOUND


class TestTree:
    def test_the_whole_forest_is_returned_flat(self, client: TestClient, mocker):
        mocker.patch.object(
            HierarchyService,
            "tree",
            return_value=HierarchyTreeResponse(root_id=None, total=1, items=[_node()]),
        )
        response = client.get("/api/v1/hierarchy/tree")
        assert response.status_code == HTTP_200_OK
        assert response.json()["items"][0]["path"] == "n1"

    def test_the_query_parameters_reach_the_service(self, client: TestClient, mocker):
        mocked = mocker.patch.object(
            HierarchyService, "tree", return_value=HierarchyTreeResponse(root_id="r", total=0, items=[])
        )
        client.get("/api/v1/hierarchy/tree?root_id=r&max_depth=2&limit=5&offset=10")
        mocked.assert_called_once_with(root_id="r", max_depth=2, limit=5, offset=10)

    def test_a_missing_root_is_404(self, client: TestClient, mocker):
        mocker.patch.object(HierarchyService, "tree", side_effect=HierarchyNodeNotFoundError("não existe"))
        assert client.get("/api/v1/hierarchy/tree?root_id=x").status_code == HTTP_404_NOT_FOUND

    def test_children_and_ancestors_are_separate_resources(self, client: TestClient, mocker):
        children = mocker.patch.object(HierarchyService, "children", return_value=[_node("c")])
        ancestors = mocker.patch.object(HierarchyService, "ancestors", return_value=[_node("a")])
        assert client.get("/api/v1/hierarchy/nodes/root/children").json()[0]["description_id"] == "c"
        assert client.get("/api/v1/hierarchy/nodes/root/ancestors").json()[0]["description_id"] == "a"
        children.assert_called_once_with("root")
        ancestors.assert_called_once_with("root")


class TestMoves:
    def test_a_move_forwards_the_parent_the_level_and_the_author(self, client: TestClient, mocker):
        mocked = mocker.patch.object(HierarchyService, "move", return_value=_node())

        response = client.post(
            "/api/v1/hierarchy/nodes/n1/move",
            json={"new_parent_id": "p1", "level_id": 4, "changed_by": "ana", "note": "Rearranjo"},
        )

        assert response.status_code == HTTP_200_OK
        command = mocked.call_args.args[1]
        assert command.new_parent_id == "p1"
        assert command.level_id == 4
        assert command.changed_by == "ana"

    def test_promoting_to_the_root_is_an_explicit_null(self, client: TestClient, mocker):
        mocked = mocker.patch.object(HierarchyService, "move", return_value=_node())
        client.post("/api/v1/hierarchy/nodes/n1/move", json={"new_parent_id": None})
        assert mocked.call_args.args[1].new_parent_id is None

    def test_a_refused_move_is_422(self, client: TestClient, mocker):
        mocker.patch.object(HierarchyService, "move", side_effect=InvalidHierarchyMoveError("isso criaria um ciclo"))
        response = client.post("/api/v1/hierarchy/nodes/n1/move", json={"new_parent_id": "p1"})
        assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY
        assert "ciclo" in response.json()["message"]


class TestDiagnostics:
    def test_the_issue_reaches_the_service(self, client: TestClient, mocker):
        from memoria_curitibana.domains.archive.schemas.hierarchy_schema import HierarchyDiagnosticListResponse

        mocked = mocker.patch.object(
            HierarchyService,
            "diagnostics",
            return_value=HierarchyDiagnosticListResponse(issue="ORPHAN", total=0, limit=50, offset=0, items=[]),
        )
        response = client.get("/api/v1/hierarchy/diagnostics?issue=ORPHAN")
        assert response.status_code == HTTP_200_OK
        mocked.assert_called_once_with(issue="ORPHAN", limit=50, offset=0)

    def test_an_unknown_issue_is_rejected_before_the_service(self, client: TestClient):
        assert client.get("/api/v1/hierarchy/diagnostics?issue=NAO_EXISTE").status_code in (
            HTTP_400_BAD_REQUEST,
            HTTP_422_UNPROCESSABLE_ENTITY,
        )


class TestProposalRoute:
    def test_the_proposal_answers_200_and_not_201(self, client: TestClient, mocker):
        """Nothing is created, so 200 is the honest status."""
        mocker.patch.object(
            HierarchyProposalService,
            "propose",
            return_value=HierarchyProposalResponse(
                total_codes=0,
                structural_codes=0,
                total_nodes=0,
                existing_nodes=0,
                nodes_to_create=0,
                ambiguous_nodes=0,
                flagged_nodes=0,
            ),
        )
        response = client.post("/api/v1/hierarchy/proposal", json={"include_existing": False, "limit": 10})
        assert response.status_code == HTTP_200_OK
        assert response.json()["total_nodes"] == 0

    def test_the_command_is_built_from_the_payload(self, client: TestClient, mocker):
        mocked = mocker.patch.object(
            HierarchyProposalService,
            "propose",
            return_value=HierarchyProposalResponse(
                total_codes=0,
                structural_codes=0,
                total_nodes=0,
                existing_nodes=0,
                nodes_to_create=0,
                ambiguous_nodes=0,
                flagged_nodes=0,
            ),
        )
        client.post("/api/v1/hierarchy/proposal", json={"include_existing": False, "limit": 10})
        command = mocked.call_args.args[0]
        assert command.include_existing is False
        assert command.limit == 10

    def test_the_flag_vocabulary_is_available_to_a_front(self, client: TestClient):
        response = client.get("/api/v1/hierarchy/flags")
        assert response.status_code == HTTP_200_OK
        assert "ORPHAN" in response.json()["issues"]


# =============================================================================
# End to end, with the real service and the real database
# =============================================================================
class TestEndToEndWithTheDatabase:
    def test_the_proposal_route_writes_nothing(
        self, client: TestClient, api_uses_test_db, db_session, seed_nobrade_levels
    ):
        """
        The promise of H3 through the router that could have written: run it and prove the
        collection did not move.
        """
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        db_session.add_all(
            [
                ArchiveDocument(
                    description_id="e2e-1",
                    original_title="Registro",
                    staging_content_hash="h",
                    reference_code="BR PRADAP IPPUC FOTOGRAFIA 00680",
                    level_id=nobrade["item"].level_id,
                ),
                ArchiveDocument(
                    description_id="e2e-2",
                    original_title="Série",
                    staging_content_hash="h",
                    reference_code="BR PRADAP IPPUC FOTOGRAFIAS",
                    level_id=nobrade["serie"].level_id,
                ),
            ]
        )
        db_session.flush()

        before = db_session.execute(ArchiveDocument.__table__.select().order_by(ArchiveDocument.description_id)).all()
        response = client.post("/api/v1/hierarchy/proposal", json={"include_existing": True, "limit": 50})
        after = db_session.execute(ArchiveDocument.__table__.select().order_by(ArchiveDocument.description_id)).all()

        assert response.status_code == HTTP_200_OK
        assert response.json()["total_codes"] == 2
        assert before == after

    def test_the_full_lifecycle_over_http(self, client: TestClient, api_uses_test_db, db_session, seed_nobrade_levels):
        """Create a root and a fund, read the tree, move the fund, read the ancestors."""
        nobrade = {level.code: level for level in seed_nobrade_levels()}

        root = client.post(
            "/api/v1/hierarchy/nodes",
            json={"reference_code": "BR PRADAP", "title": "Acervo", "level_id": nobrade["acervo"].level_id},
        )
        assert root.status_code == HTTP_201_CREATED
        root_id = root.json()["description_id"]

        fund = client.post(
            "/api/v1/hierarchy/nodes",
            json={
                "reference_code": "BR PRADAP SMU",
                "title": "SMU",
                "level_id": nobrade["fundo"].level_id,
                "parent_id": root_id,
            },
        )
        assert fund.status_code == HTTP_201_CREATED
        fund_id = fund.json()["description_id"]

        tree = client.get(f"/api/v1/hierarchy/tree?root_id={root_id}")
        assert tree.json()["total"] == 2

        ancestors = client.get(f"/api/v1/hierarchy/nodes/{fund_id}/ancestors")
        assert [item["description_id"] for item in ancestors.json()] == [root_id]

        # A Dossiê at the root is refused: the ladder is enforced on the way in.
        refused = client.post(
            "/api/v1/hierarchy/nodes",
            json={"reference_code": "BR PRADAP D9", "title": "Dossiê", "level_id": nobrade["dossie"].level_id},
        )
        assert refused.status_code == HTTP_422_UNPROCESSABLE_ENTITY
