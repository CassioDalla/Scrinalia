"""HTTP surface of the description hierarchy (Fase 2.5, H1—H3)."""

from typing import Literal

from litestar import Controller, delete, get, patch, post
from litestar.di import NamedDependency, Provide
from litestar.params import FromPath, FromQuery

from memoria_curitibana.api.dependencies import (
    provide_hierarchy_materialisation_service,
    provide_hierarchy_proposal_service,
    provide_hierarchy_service,
    provide_level_catalog_service,
)
from memoria_curitibana.api.schemas.hierarchy_requests import (
    DescriptionLevelCreateRequest,
    DescriptionLevelUpdateRequest,
    HierarchyMaterialisationRequest,
    HierarchyNodeCreateRequest,
    HierarchyNodeMoveRequest,
    HierarchyPlanDecisionRequest,
    HierarchyProposalRequest,
)
from memoria_curitibana.domains.archive.domain.hierarchy import HierarchyIssue
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    CreateDescriptionLevelCommand,
    CreateHierarchyNodeCommand,
    DescriptionLevelDTO,
    HierarchyDiagnosticListResponse,
    HierarchyMaterialisationLogListResponse,
    HierarchyMaterialisationPreview,
    HierarchyMaterialisationResult,
    HierarchyNodeDetail,
    HierarchyNodePlanDTO,
    HierarchyNodeSummary,
    HierarchyPlanDecisionCommand,
    HierarchyPlanListResponse,
    HierarchyPlanSuggestionResponse,
    HierarchyProposalCommand,
    HierarchyProposalResponse,
    HierarchyTreeResponse,
    MoveNodeCommand,
    UpdateDescriptionLevelCommand,
)
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    HierarchyMaterialisationRequest as MaterialisationCommand,
)
from memoria_curitibana.domains.archive.services.hierarchy_materialisation_service import (
    HierarchyMaterialisationService,
)
from memoria_curitibana.domains.archive.services.hierarchy_proposal_service import HierarchyProposalService
from memoria_curitibana.domains.archive.services.hierarchy_service import HierarchyService
from memoria_curitibana.domains.archive.services.level_catalog_service import LevelCatalogService


class HierarchyController(Controller):
    """
    The arrangement of the collection: the ladder of levels, the tree, and the proposal.

    Deliberately separate from ``TaxonomyController``: hierarchy is *provenance and arrangement*
    (objective, one place per description, read from the reference code), while the taxonomy is
    *subject* (interpretative, several per description, written by the AI). Putting them in one
    controller would invite exactly the confusion the roadmap warns about.
    """

    path = "/api/v1/hierarchy"
    tags = ["Hierarchy"]  # noqa: RUF012

    dependencies = {  # noqa: RUF012
        "level_service": Provide(provide_level_catalog_service, sync_to_thread=False),
        "hierarchy_service": Provide(provide_hierarchy_service, sync_to_thread=False),
        "proposal_service": Provide(provide_hierarchy_proposal_service, sync_to_thread=False),
        "materialisation_service": Provide(provide_hierarchy_materialisation_service, sync_to_thread=False),
    }

    # =========================================================================
    # H1 — Level catalogue
    # =========================================================================
    @get("/levels", sync_to_thread=True)
    def list_levels(
        self,
        level_service: NamedDependency[LevelCatalogService],
        only_active: FromQuery[bool] = False,
    ) -> list[DescriptionLevelDTO]:
        """Lists the ladder of description levels, with how many descriptions sit on each rung."""
        return level_service.list_levels(only_active=only_active)

    @post("/levels", status_code=201, sync_to_thread=True)
    def create_level(
        self,
        level_service: NamedDependency[LevelCatalogService],
        data: DescriptionLevelCreateRequest,
    ) -> DescriptionLevelDTO:
        """Registers a rung. A taken ordinal, code or name is rejected with 409."""
        return level_service.create_level(CreateDescriptionLevelCommand(**data.model_dump()))

    @patch("/levels/{level_id:int}", sync_to_thread=True)
    def update_level(
        self,
        level_service: NamedDependency[LevelCatalogService],
        level_id: FromPath[int],
        data: DescriptionLevelUpdateRequest,
    ) -> DescriptionLevelDTO:
        """Renames, re-describes, edits the aliases or (de)activates a rung. Levels are never deleted."""
        return level_service.update_level(
            level_id, UpdateDescriptionLevelCommand(**data.model_dump(exclude_unset=True))
        )

    # =========================================================================
    # H2 — The tree
    # =========================================================================
    @get("/tree", sync_to_thread=True)
    def get_tree(
        self,
        hierarchy_service: NamedDependency[HierarchyService],
        root_id: FromQuery[str | None] = None,
        max_depth: FromQuery[int | None] = None,
        limit: FromQuery[int] = 200,
        offset: FromQuery[int] = 0,
    ) -> HierarchyTreeResponse:
        """
        The arrangement, flat and ordered by path.

        A subtree is one indexed ``path LIKE 'x.%'``: that is the query the navigation makes
        constantly, and the whole reason the path is materialised instead of walked per level.
        """
        return hierarchy_service.tree(root_id=root_id, max_depth=max_depth, limit=limit, offset=offset)

    @get("/nodes/{description_id:str}", sync_to_thread=True)
    def get_node(
        self,
        hierarchy_service: NamedDependency[HierarchyService],
        description_id: FromPath[str],
    ) -> HierarchyNodeDetail:
        """
        One description as a place in the arrangement: the node, its branch and its children.

        This is what the individual edit (H5) reads before moving a node or correcting its rung —
        the branch it sits on and what would travel with it, in one round trip.
        """
        return hierarchy_service.node(description_id)

    @get("/nodes/{description_id:str}/children", sync_to_thread=True)
    def list_children(
        self,
        hierarchy_service: NamedDependency[HierarchyService],
        description_id: FromPath[str],
    ) -> list[HierarchyNodeSummary]:
        """Direct children of one description."""
        return hierarchy_service.children(description_id)

    @get("/nodes/{description_id:str}/ancestors", sync_to_thread=True)
    def list_ancestors(
        self,
        hierarchy_service: NamedDependency[HierarchyService],
        description_id: FromPath[str],
    ) -> list[HierarchyNodeSummary]:
        """Ancestors of one description, root first, read from the materialised path."""
        return hierarchy_service.ancestors(description_id)

    @post("/nodes", status_code=201, sync_to_thread=True)
    def create_node(
        self,
        hierarchy_service: NamedDependency[HierarchyService],
        data: HierarchyNodeCreateRequest,
    ) -> HierarchyNodeSummary:
        """
        Creates a fund, section or series the source never delivered.

        The same rules as a move are validated against the chosen parent: the ladder is enforced
        on the way in, not repaired afterwards.
        """
        return hierarchy_service.create_node(CreateHierarchyNodeCommand(**data.model_dump()))

    @post("/nodes/{description_id:str}/move", status_code=200, sync_to_thread=True)
    def move_node(
        self,
        hierarchy_service: NamedDependency[HierarchyService],
        description_id: FromPath[str],
        data: HierarchyNodeMoveRequest,
    ) -> HierarchyNodeSummary:
        """
        Reparents and/or re-levels a description, rewriting the path of its whole subtree.

        Cycle, ladder order and "this level admits no children" are all refused with 422 — the
        tree is validated before it is written, and the whole subtree moves in one statement.
        """
        return hierarchy_service.move(
            description_id,
            MoveNodeCommand(
                new_parent_id=data.new_parent_id,
                level_id=data.level_id,
                changed_by=data.changed_by,
                note=data.note,
            ),
        )

    # =========================================================================
    # Diagnostics
    # =========================================================================
    @get("/diagnostics", sync_to_thread=True)
    def list_diagnostics(
        self,
        hierarchy_service: NamedDependency[HierarchyService],
        issue: FromQuery[
            Literal["ORPHAN", "DOSSIER_WITHOUT_PARENT", "UNKNOWN_LEVEL", "PATH_DIVERGENCE", "LEVEL_DEPTH_MISMATCH"]
        ] = "ORPHAN",
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> HierarchyDiagnosticListResponse:
        """
        One page of structural problems, plus the total for the same filter.

        ``LEVEL_DEPTH_MISMATCH`` learns the depth-to-level norm **from the collection** and flags
        the minority: the measurement says no depth-to-level mapping can be hardcoded, because five
        tokens hold 2,466 Items, one Série and one Seção at the same time.
        """
        return hierarchy_service.diagnostics(issue=issue, limit=limit, offset=offset)

    # =========================================================================
    # H3 — Proposal (read-only)
    # =========================================================================
    @post("/proposal", status_code=200, sync_to_thread=True)
    def propose_tree(
        self,
        proposal_service: NamedDependency[HierarchyProposalService],
        data: HierarchyProposalRequest,
    ) -> HierarchyProposalResponse:
        """
        Reads the reference codes and returns the tree they imply. **Nothing is written.**

        The archivist reviews this before any node exists; every ordinal that no declared record
        anchors comes back as ``ORDINAL_INFERRED``, and a plural/singular collision such as
        ``FOTOGRAFIA``/``FOTOGRAFIAS`` comes back as ``NEAR_DUPLICATE_NODE`` instead of being
        resolved by a similarity score.
        """
        return proposal_service.propose(HierarchyProposalCommand(**data.model_dump()))

    @get("/flags", sync_to_thread=True)
    def list_flags(self) -> dict[str, list[str]]:
        """The vocabularies the diagnostics and the proposal speak, so a front can group by them."""
        return {
            "issues": [str(issue) for issue in HierarchyIssue],
            "diagnostics": [
                "ORPHAN",
                "DOSSIER_WITHOUT_PARENT",
                "UNKNOWN_LEVEL",
                "PATH_DIVERGENCE",
                "LEVEL_DEPTH_MISMATCH",
            ],
        }

    # =========================================================================
    # H4 — Materialising the tree, driven by a recorded decision
    # =========================================================================
    @post("/plans/suggest", status_code=200, sync_to_thread=True)
    def suggest_plans(
        self,
        materialisation_service: NamedDependency[HierarchyMaterialisationService],
    ) -> HierarchyPlanSuggestionResponse:
        """
        Writes the proposed rungs into the catalogue. Nothing is created in the collection.

        Idempotent by code, and it **never overwrites a decision**: a rung the archivist approved
        or rejected comes back exactly as they left it, so the same ~52 questions are not asked
        again on every run.
        """
        return materialisation_service.suggest()

    @get("/plans", sync_to_thread=True)
    def list_plans(
        self,
        materialisation_service: NamedDependency[HierarchyMaterialisationService],
        status: FromQuery[Literal["SUGGESTED", "APPROVED", "REJECTED"] | None] = None,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> HierarchyPlanListResponse:
        """One page of the rungs, with the evidence and the decision about each."""
        return materialisation_service.list_plans(status=status, limit=limit, offset=offset)

    @patch("/plans/{plan_id:int}", sync_to_thread=True)
    def decide_plan(
        self,
        materialisation_service: NamedDependency[HierarchyMaterialisationService],
        plan_id: FromPath[int],
        data: HierarchyPlanDecisionRequest,
    ) -> HierarchyNodePlanDTO:
        """
        Records the verdict on one rung: its level, its title, or that it **is** another rung.

        ``collapse_into_code`` is where the archivist corrects what the code cannot know. The
        measured example: ``BR PRADAP SMU ED AL`` and ``BR PRADAP SMU ED AL CONSTR`` are one level
        of the arrangement ("Alvenaria - Construções") — nothing in the string says so.
        """
        return materialisation_service.decide(plan_id, HierarchyPlanDecisionCommand(**data.model_dump()))

    @post("/materialisation/preview", status_code=200, sync_to_thread=True)
    def preview_materialisation(
        self,
        materialisation_service: NamedDependency[HierarchyMaterialisationService],
        data: HierarchyMaterialisationRequest,
    ) -> HierarchyMaterialisationPreview:
        """
        The dry run: what the approved decisions would create and move. **Nothing is written.**

        Computed by the same planner the apply executes, so the number the archivist approves is
        the number the write produces.
        """
        return materialisation_service.preview(MaterialisationCommand(**data.model_dump()))

    @post("/materialisation/apply", status_code=200, sync_to_thread=True)
    def apply_materialisation(
        self,
        materialisation_service: NamedDependency[HierarchyMaterialisationService],
        data: HierarchyMaterialisationRequest,
    ) -> HierarchyMaterialisationResult:
        """
        Creates the missing rungs, adopts the existing ones and hangs the descriptions under them.

        Every run is logged with the exact previous state, so ``DELETE /materialisation/log/{id}``
        can reverse it: a decision a human took, a human can undo.
        """
        return materialisation_service.apply(MaterialisationCommand(**data.model_dump()))

    @get("/materialisation/log", sync_to_thread=True)
    def list_materialisation_log(
        self,
        materialisation_service: NamedDependency[HierarchyMaterialisationService],
        include_undone: FromQuery[bool] = True,
        limit: FromQuery[int] = 50,
        offset: FromQuery[int] = 0,
    ) -> HierarchyMaterialisationLogListResponse:
        """The audit trail of the materialisations: what was created, how much moved, by whom."""
        return materialisation_service.list_log(include_undone=include_undone, limit=limit, offset=offset)

    @delete("/materialisation/log/{materialisation_id:int}", status_code=200, sync_to_thread=True)
    def undo_materialisation(
        self,
        materialisation_service: NamedDependency[HierarchyMaterialisationService],
        materialisation_id: FromPath[int],
        undone_by: FromQuery[str | None] = None,
    ) -> dict:
        """
        Reverses one run: the descriptions go back where they were, then the created rungs go.

        The second attempt is **409** and an unknown id is **404**; the ledger entry is never
        deleted, so "this was materialised, then reversed" survives the reversal.
        """
        entry = materialisation_service.undo(materialisation_id, undone_by=undone_by)
        return {
            "message": f"Materialização {materialisation_id} desfeita: {entry.changed_rows} descrições voltaram ao lugar.",
            "data": entry.model_dump(),
        }
