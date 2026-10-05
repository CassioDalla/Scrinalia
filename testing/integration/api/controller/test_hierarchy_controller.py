"""
HTTP contract of the hierarchy controller.

Two layers are pinned here on purpose:

* the **wiring and the status codes**, with the services mocked, so the HTTP surface is asserted
  without a database; and
* one **end-to-end path** with the real service and the real database (`api_uses_test_db`), because the
  contract that matters most — "the proposal writes nothing" — is only meaningful through the
  router that could have written.
"""

from typing import get_args

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

from memoria_curitibana.api.controllers.hierarchy_controller import DiagnosticIssue, PlanStatusFilter
from memoria_curitibana.asgi import create_app
from memoria_curitibana.domains.archive.domain.hierarchy import (
    HierarchyIssue,
    HierarchyViolation,
    PlanStatus,
    ProposalFlag,
)
from memoria_curitibana.domains.archive.exceptions import (
    DescriptionLevelNotFoundError,
    DuplicateDescriptionLevelError,
    HierarchyNodeNotFoundError,
    HierarchyPlanNotFoundError,
    InvalidHierarchyMoveError,
    InvalidHierarchyPlanError,
    MaterialisationAlreadyUndoneError,
    MaterialisationNotFoundError,
)
from memoria_curitibana.domains.archive.models import ArchiveDocument
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    DescriptionLevelDTO,
    HierarchyMaterialisationLogListResponse,
    HierarchyMaterialisationPreview,
    HierarchyMaterialisationResult,
    HierarchyNodePlanDTO,
    HierarchyNodeSummary,
    HierarchyPlanListResponse,
    HierarchyPlanSuggestionResponse,
    HierarchyProposalResponse,
    HierarchyTreeResponse,
)
from memoria_curitibana.domains.archive.services.hierarchy_materialisation_service import (
    HierarchyMaterialisationService,
)
from memoria_curitibana.domains.archive.services.hierarchy_proposal_service import HierarchyProposalService
from memoria_curitibana.domains.archive.services.hierarchy_service import DIAGNOSTIC_ISSUES, HierarchyService
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

    def test_the_summary_is_served_without_a_page(self, client: TestClient, mocker):
        """The section counts come from the service in one request, not from five pages."""
        from memoria_curitibana.domains.archive.schemas.hierarchy_schema import HierarchyDiagnosticSummary

        mocked = mocker.patch.object(
            HierarchyService,
            "diagnostic_summary",
            return_value=HierarchyDiagnosticSummary(counts={"ORPHAN": 3602, "PATH_DIVERGENCE": 0}),
        )
        response = client.get("/api/v1/hierarchy/diagnostics/summary")
        assert response.status_code == HTTP_200_OK
        assert response.json()["counts"]["ORPHAN"] == 3602
        mocked.assert_called_once_with()

    def test_the_route_vocabulary_matches_the_service(self):
        """
        The contract lists what the endpoint accepts; the service decides what it answers.

        Two definitions because a route signature needs a ``Literal`` and the service needs a tuple;
        a value added to one and forgotten in the other would let a client ask for an issue that
        answers 422, which is exactly the defect ``/flags`` used to carry.
        """
        assert set(get_args(DiagnosticIssue)) == set(DIAGNOSTIC_ISSUES)
        assert set(get_args(PlanStatusFilter)) == {str(status) for status in PlanStatus}


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
        """Every vocabulary the arrangement screens group by, so the front embeds none of them."""
        response = client.get("/api/v1/hierarchy/flags")
        assert response.status_code == HTTP_200_OK
        body = response.json()
        assert body["issues"] == list(DIAGNOSTIC_ISSUES)
        # NEAR_DUPLICATE_NODE is a statement about codes the tree does not contain yet: the
        # diagnostics endpoint refuses it, so advertising it here would send the front to a 422.
        assert "NEAR_DUPLICATE_NODE" not in body["issues"]
        assert set(body["plan_statuses"]) == {str(status) for status in PlanStatus}
        assert "ORDINAL_INFERRED" in body["plan_flags"]
        assert "CYCLE" in body["violations"]

    def test_the_plan_flag_vocabulary_covers_every_writer(self, client: TestClient):
        """
        A plan row's ``flags`` is assembled from four vocabularies, and all four must be published.

        This is the defect the screen found: the route advertised only ``ProposalFlag``, so
        ``NEAR_DUPLICATE_NODE`` — which the real collection carries — was rendered as a raw code.
        Pinning the union here means a vocabulary added to the proposal and forgotten in the route
        fails the suite instead of reaching the archivist as an untranslated string.
        """
        from memoria_curitibana.domains.archive.domain.hierarchy_code import CodeFlag

        body = client.get("/api/v1/hierarchy/flags").json()
        assert set(body["plan_flags"]) == (
            {str(flag) for flag in ProposalFlag}
            | {str(HierarchyIssue.NEAR_DUPLICATE_NODE)}
            | {str(HierarchyViolation.LEVEL_NOT_ALLOWED_AS_CHILD)}
            | {str(flag) for flag in CodeFlag}
        )


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


class TestThePlanCatalogueOverHttp:
    def test_suggesting_registers_the_rungs(self, client: TestClient, mocker):
        mocker.patch.object(
            HierarchyMaterialisationService,
            "suggest",
            return_value=HierarchyPlanSuggestionResponse(created=52, refreshed=0, preserved=0, total=52),
        )
        response = client.post("/api/v1/hierarchy/plans/suggest")
        assert response.status_code == HTTP_200_OK
        assert response.json()["created"] == 52

    def test_the_status_filter_reaches_the_service(self, client: TestClient, mocker):
        mocked = mocker.patch.object(
            HierarchyMaterialisationService,
            "list_plans",
            return_value=HierarchyPlanListResponse(total=0, limit=10, offset=0, items=[]),
        )
        client.get("/api/v1/hierarchy/plans?status=APPROVED&limit=10")
        mocked.assert_called_once_with(status="APPROVED", limit=10, offset=0)

    def test_a_decision_is_forwarded_with_the_collapse(self, client: TestClient, mocker):
        """``collapse_into_code`` is how the archivist says AL and CONSTR are one level."""
        mocked = mocker.patch.object(HierarchyMaterialisationService, "decide", return_value=_plan_dto())
        response = client.patch(
            "/api/v1/hierarchy/plans/7",
            json={"status": "APPROVED", "level_id": 4, "collapse_into_code": "BR PRADAP SMU ED AL"},
        )

        assert response.status_code == HTTP_200_OK
        command = mocked.call_args.args[1]
        assert command.status == "APPROVED"
        assert command.collapse_into_code == "BR PRADAP SMU ED AL"

    def test_an_unknown_plan_is_404(self, client: TestClient, mocker):
        mocker.patch.object(
            HierarchyMaterialisationService, "decide", side_effect=HierarchyPlanNotFoundError("não existe")
        )
        response = client.patch("/api/v1/hierarchy/plans/999", json={"status": "APPROVED"})
        assert response.status_code == HTTP_404_NOT_FOUND

    def test_an_impossible_decision_is_422(self, client: TestClient, mocker):
        mocker.patch.object(
            HierarchyMaterialisationService,
            "decide",
            side_effect=InvalidHierarchyPlanError("Aprovar um nó exige escolher o nível"),
        )
        response = client.patch("/api/v1/hierarchy/plans/7", json={"status": "APPROVED"})
        assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY


class TestMaterialisationOverHttp:
    def test_the_preview_answers_200_and_writes_nothing(self, client: TestClient, mocker):
        mocker.patch.object(
            HierarchyMaterialisationService,
            "preview",
            return_value=HierarchyMaterialisationPreview(
                nodes_to_create=5,
                nodes_to_adopt=1,
                nodes_already_materialised=0,
                documents_to_attach=5,
                documents_already_placed=0,
                remaining_orphans=0,
            ),
        )
        response = client.post("/api/v1/hierarchy/materialisation/preview", json={"limit": 10})
        assert response.status_code == HTTP_200_OK
        assert response.json()["nodes_to_create"] == 5

    def test_the_apply_answers_200_and_reports_the_ledger_id(self, client: TestClient, mocker):
        mocker.patch.object(
            HierarchyMaterialisationService,
            "apply",
            return_value=HierarchyMaterialisationResult(
                materialisation_id=3,
                created_nodes=5,
                adopted_nodes=1,
                documents_attached=5,
                rung_map_size=8,
            ),
        )
        response = client.post("/api/v1/hierarchy/materialisation/apply", json={"changed_by": "ana"})
        assert response.status_code == HTTP_200_OK
        assert response.json()["materialisation_id"] == 3

    def test_undone_entries_can_be_hidden(self, client: TestClient, mocker):
        mocked = mocker.patch.object(
            HierarchyMaterialisationService,
            "list_log",
            return_value=HierarchyMaterialisationLogListResponse(total=0, limit=50, offset=0, items=[]),
        )
        client.get("/api/v1/hierarchy/materialisation/log?include_undone=false")
        mocked.assert_called_once_with(include_undone=False, limit=50, offset=0)

    def test_undoing_twice_is_409(self, client: TestClient, mocker):
        mocker.patch.object(
            HierarchyMaterialisationService,
            "undo",
            side_effect=MaterialisationAlreadyUndoneError("já foi desfeita"),
        )
        assert client.delete("/api/v1/hierarchy/materialisation/log/3").status_code == HTTP_409_CONFLICT

    def test_an_unknown_run_is_404(self, client: TestClient, mocker):
        mocker.patch.object(
            HierarchyMaterialisationService, "undo", side_effect=MaterialisationNotFoundError("não existe")
        )
        assert client.delete("/api/v1/hierarchy/materialisation/log/999").status_code == HTTP_404_NOT_FOUND


def _plan_dto() -> HierarchyNodePlanDTO:
    return HierarchyNodePlanDTO(
        plan_id=7,
        code="BR PRADAP SMU ED AL CONSTR",
        depth=6,
        status="APPROVED",
        level_id=4,
    )
