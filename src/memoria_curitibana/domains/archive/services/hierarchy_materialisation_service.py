"""
Materialising the arrangement, driven by a recorded human decision (Fase 2.5, H4).

The proposal (H3) reads the codes and says what tree they imply. This is what turns that reading
into rows — and it exists because **the code cannot be trusted alone**. The canonical case came
from the archivist: ``BR PRADAP SMU ED AL CONSTR`` splits into two alphabetic segments that are, in
the real arrangement, one level ("Alvenaria - Construções"). No slicer can know that; the evidence
is not in the string. So:

* the machine proposes a rung and the archivist decides its level, its title and, crucially,
  whether it **is the same rung as another** (``collapse_into_code``);
* the decision is persisted, so a new suggestion run never asks the same question twice;
* nothing is written before a **dry run** the archivist can read;
* every applied run is logged with the exact previous state, so a human can undo what a human
  authorised.

The planner is shared by the preview and the apply on purpose: a number the curator approved has
to be the number the write produces. A dry run that lies is worse than no dry run.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from memoria_curitibana.domains.archive.domain.hierarchy import (
    collapse_chain,
    resolve_rung,
)
from memoria_curitibana.domains.archive.domain.hierarchy_code import (
    normalize_reference_code,
    parent_rung_code,
    slice_reference_code,
)
from memoria_curitibana.domains.archive.exceptions import (
    DescriptionLevelNotFoundError,
    HierarchyPlanNotFoundError,
    InvalidHierarchyPlanError,
    MaterialisationAlreadyUndoneError,
    MaterialisationNotFoundError,
)
from memoria_curitibana.domains.archive.models import (
    ArchiveHierarchyMaterialisationLog,
    ArchiveHierarchyNodePlan,
)
from memoria_curitibana.domains.archive.repository.hierarchy_repo import CodeObservation, HierarchyRepository
from memoria_curitibana.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    CreateHierarchyNodeCommand,
    HierarchyMaterialisationItem,
    HierarchyMaterialisationLogDTO,
    HierarchyMaterialisationLogListResponse,
    HierarchyMaterialisationPreview,
    HierarchyMaterialisationRequest,
    HierarchyMaterialisationResult,
    HierarchyNodePlanDTO,
    HierarchyPlanDecisionCommand,
    HierarchyPlanListResponse,
    HierarchyPlanSuggestionResponse,
    HierarchyProposalCommand,
)
from memoria_curitibana.domains.archive.services.hierarchy_proposal_service import HierarchyProposalService

ACTION_CREATE = "CREATE"
ACTION_ADOPT = "ADOPT"
ACTION_ALREADY = "ALREADY"


@dataclass
class _Rung:
    """One approved rung and what the run would do with it."""

    code: str
    action: str
    node_id: str | None
    node_path: str | None
    parent_code: str | None
    level_id: int | None
    level_name: str | None
    title: str | None
    reference_code: str | None
    document_ids: list[str] = field(default_factory=list)
    rooted_early: bool = False


@dataclass
class _Plan:
    """The whole decision, resolved: what to create, what to adopt and who hangs where."""

    rungs: list[_Rung] = field(default_factory=list)
    node_parents: dict[str, str | None] = field(default_factory=dict)
    rung_map: dict[str, str] = field(default_factory=dict)
    document_targets: dict[str, list[str]] = field(default_factory=dict)
    documents_already_placed: int = 0
    orphan_ids: list[str] = field(default_factory=list)
    attached_node_ids: list[str] = field(default_factory=list)

    @property
    def to_create(self) -> list[_Rung]:
        return [rung for rung in self.rungs if rung.action == ACTION_CREATE]

    @property
    def documents_to_attach(self) -> int:
        return sum(len(ids) for ids in self.document_targets.values())


class HierarchyMaterialisationService:
    def __init__(
        self,
        repo: HierarchyRepository,
        catalog: LevelCatalogRepository,
        proposal: HierarchyProposalService | None = None,
    ) -> None:
        self.repo = repo
        self.catalog = catalog
        self._proposal = proposal

    # =========================================================================
    # The catalogue of decisions
    # =========================================================================
    def suggest(self) -> HierarchyPlanSuggestionResponse:
        """
        Writes the proposed rungs into the catalogue, idempotently.

        A row a human already decided is left exactly as the human left it — including its level
        and its title — so the same ~52 questions are not asked again on every run. Only the
        evidence of a still-``SUGGESTED`` row is refreshed.
        """
        proposal = self._proposal_service().propose(HierarchyProposalCommand(include_existing=True, limit=5000))

        created = refreshed = preserved = 0
        for node in proposal.nodes:
            evidence = {
                "depth": node.depth,
                "parent_code": node.parent_code,
                "document_count": node.document_count,
                "declared_levels": node.declared_levels,
                "flags": node.flags,
                "sample_description_ids": node.sample_description_ids,
                "existing_description_id": node.existing_description_id,
                # A proposal while SUGGESTED, frozen once the archivist decides.
                "level_id": node.proposed_level_id,
                "title": node.suggested_name,
                "reference_code": node.code,
            }
            _plan, was_created, was_refreshed = self.repo.upsert_plan(node.code, evidence)
            created += int(was_created)
            refreshed += int(was_refreshed)
            preserved += int(not was_created and not was_refreshed)

        return HierarchyPlanSuggestionResponse(
            created=created,
            refreshed=refreshed,
            preserved=preserved,
            total=self.repo.count_plans(),
        )

    def list_plans(self, status: str | None, limit: int, offset: int) -> HierarchyPlanListResponse:
        plans, total = self.repo.list_plans(status=status, limit=limit, offset=offset)
        levels = {level.level_id: level.name for level in self.catalog.list_levels()}
        return HierarchyPlanListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=[self._to_dto(plan, levels) for plan in plans],
            # The count of the whole catalogue travels with every page, so the progress the screen
            # shows is about the 52 rungs and not about the 20 it happens to be displaying.
            status_counts=self.repo.count_plans_by_status(),
        )

    def decide(self, plan_id: int, command: HierarchyPlanDecisionCommand) -> HierarchyNodePlanDTO:
        """
        Records the archivist's verdict, refusing the decisions that cannot be materialised.

        Approving a rung means choosing a level and, when the rung has to be created, being able to
        say what it is. A collapse has to point at a rung that exists in the catalogue and must not
        close a loop: the apply follows the links, and a contradiction there would produce a tree
        nobody asked for.
        """
        plan = self.repo.get_plan(plan_id)
        if plan is None:
            raise HierarchyPlanNotFoundError(f"Plano de nó {plan_id} não existe no catálogo.")

        if command.collapse_into_code is not None:
            # An empty string is how a client undoes a collapse; ``None`` means "not sent".
            target = command.collapse_into_code.strip() or None
            plan.collapse_into_code = target
            if target is not None:
                self._validate_collapse(plan, target)

        if command.level_id is not None and self.catalog.get(command.level_id) is None:
            raise DescriptionLevelNotFoundError(f"Nível de descrição {command.level_id} não existe no catálogo.")

        if command.title is not None:
            plan.title = command.title or None
        if command.reference_code is not None:
            plan.reference_code = command.reference_code or None
        if command.level_id is not None:
            plan.level_id = command.level_id

        if command.status == "APPROVED" and plan.level_id is None:
            raise InvalidHierarchyPlanError(
                "Aprovar um nó exige escolher o nível de descrição: é a decisão que o código não sabe tomar."
            )

        plan.status = str(command.status)
        plan.decided_by = command.decided_by
        plan.decision_note = command.note
        if command.status != "SUGGESTED":
            plan.decided_at = datetime.now(UTC)
        self.repo.db.flush()

        levels = {level.level_id: level.name for level in self.catalog.list_levels()}
        return self._to_dto(plan, levels)

    def _validate_collapse(self, plan: ArchiveHierarchyNodePlan, target: str) -> None:
        if target == plan.code:
            raise InvalidHierarchyPlanError("Um nó não pode ser fundido nele mesmo.")
        if self.repo.get_plan_by_code(target) is None:
            raise InvalidHierarchyPlanError(
                f"O nó '{target}' não existe no catálogo: funda apenas em rungs que a proposta conhece."
            )
        # Walking from the target must not arrive back here.
        collapse_map = {
            code: other.collapse_into_code for code, other in self.repo.all_plans().items() if other.collapse_into_code
        }
        collapse_map[plan.code] = target
        if collapse_chain(target, collapse_map) == plan.code:
            raise InvalidHierarchyPlanError("Fundir assim criaria um ciclo entre rungs.")

    # =========================================================================
    # Preview and apply share this planner
    # =========================================================================
    def preview(self, request: HierarchyMaterialisationRequest) -> HierarchyMaterialisationPreview:
        plan = self._plan()
        items = self._items(plan, limit=request.limit)
        return HierarchyMaterialisationPreview(
            nodes_to_create=len(plan.to_create),
            nodes_to_adopt=len([rung for rung in plan.rungs if rung.action == ACTION_ADOPT]),
            nodes_already_materialised=len([rung for rung in plan.rungs if rung.action == ACTION_ALREADY]),
            documents_to_attach=plan.documents_to_attach,
            documents_already_placed=plan.documents_already_placed,
            remaining_orphans=len(plan.orphan_ids),
            items=items,
        )

    def apply(self, request: HierarchyMaterialisationRequest) -> HierarchyMaterialisationResult:
        """
        Creates the missing rungs, adopts the existing ones and hangs the descriptions under them.

        The order is the whole difficulty: parents before children (the self-reference is
        ``RESTRICT`` and a path is built from its parent's), the previous state captured **before**
        the first write, and the paths recomputed in group statements rather than row by row.
        """
        plan = self._plan()
        if not plan.rungs:
            raise InvalidHierarchyPlanError(
                "Nenhum nó aprovado: aprove ao menos uma rung antes de materializar a árvore."
            )

        created_nodes: list[dict] = []
        nodes: dict[str, str] = {}
        paths: dict[str, str] = {}

        # 1. Nodes that have to exist before anything can point at them.
        for rung in plan.to_create:
            node = self.repo.create_node(
                CreateHierarchyNodeCommand(
                    reference_code=rung.reference_code or rung.code,
                    title=rung.title or rung.code,
                    level_id=rung.level_id,
                ),
                None,
            )
            nodes[rung.code] = node.description_id
            paths[rung.code] = node.description_id
            created_nodes.append(
                {
                    "description_id": node.description_id,
                    "code": rung.code,
                    "level_id": rung.level_id,
                    "title": node.original_title,
                }
            )

        # 2. Nodes that already exist: adopting one leaves the description where it is until its
        #    own parent is resolved below.
        for rung in plan.rungs:
            if rung.action == ACTION_CREATE:
                continue
            if rung.node_id is None:
                raise InvalidHierarchyPlanError(
                    f"O nó '{rung.code}' deveria existir e não existe: a árvore não pode ser materializada."
                )
            nodes[rung.code] = rung.node_id
            paths[rung.code] = rung.node_path or rung.node_id

        # 3. Everything that is about to move, captured before the first write. A node whose parent
        #    is already the decided one is not touched, so the ledger records changes and not intent.
        node_state = self.repo.capture_state([nodes[code] for code in plan.node_parents])
        node_moves = {
            code: parent_code
            for code, parent_code in plan.node_parents.items()
            if parent_code is not None and node_state.get(nodes[code], {}).get("parent_id") != nodes[parent_code]
        }
        moving_documents = [doc_id for ids in plan.document_targets.values() for doc_id in ids]
        previous_state = self.repo.capture_state([*moving_documents, *[nodes[code] for code in node_moves]])

        # 4. Parents first, iteratively: a node can only be attached once its parent's path is final.
        pending: dict[str, str] = dict(node_moves)
        settled = {code for code, parent_code in plan.node_parents.items() if parent_code is None}
        while pending:
            progressed = False
            for code in list(pending):
                parent_code = pending[code]
                if parent_code not in settled:
                    continue
                self.repo.attach_group([nodes[code]], nodes[parent_code], paths[parent_code])
                paths[code] = self._child_path(paths[parent_code], nodes[code])
                settled.add(code)
                del pending[code]
                progressed = True
            if not progressed:
                # A collapse ring the decision should not have allowed. Leave the rest at the root
                # instead of looping: the diagnostics will show it.
                break

        # 5. The descriptions themselves, one statement per rung.
        documents_attached = 0
        for code, description_ids in plan.document_targets.items():
            documents_attached += self.repo.attach_group(description_ids, nodes[code], paths[code])

        # 6. The ledger, and the plans know what they produced.
        entry = self.repo.create_materialisation_log(
            created_nodes=created_nodes,
            rung_map=plan.rung_map,
            previous_state=previous_state,
            changed_by=request.changed_by,
            note=request.note,
        )
        for rung in plan.rungs:
            stored = self.repo.get_plan_by_code(rung.code)
            if stored is not None:
                stored.materialised_description_id = nodes[rung.code]
        self.repo.db.flush()

        return HierarchyMaterialisationResult(
            materialisation_id=entry.materialisation_id,
            created_nodes=len(created_nodes),
            adopted_nodes=len([rung for rung in plan.rungs if rung.action == ACTION_ADOPT]),
            documents_attached=documents_attached,
            rung_map_size=len(plan.rung_map),
            items=self._items(plan, limit=request.limit),
        )

    def list_log(self, include_undone: bool, limit: int, offset: int) -> HierarchyMaterialisationLogListResponse:
        entries, total = self.repo.list_materialisation_logs(include_undone, limit, offset)
        return HierarchyMaterialisationLogListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=[self._to_log_dto(entry) for entry in entries],
        )

    def undo(self, materialisation_id: int, undone_by: str | None) -> HierarchyMaterialisationLogDTO:
        """
        Reverses one run: every moved description goes back where it was, then the created nodes go.

        The order is not cosmetic. The self-reference is ``RESTRICT``, so a created node cannot be
        removed while anything still points at it — restoring first is what makes deleting possible.
        And the undo refuses when a later run attached something the ledger does not know about,
        because reversing then would silently detach work that was never part of this decision.
        """
        entry = self.repo.get_materialisation_log(materialisation_id)
        if entry is None:
            raise MaterialisationNotFoundError(f"Materialização {materialisation_id} não existe no ledger.")
        if entry.undone_at is not None:
            raise MaterialisationAlreadyUndoneError(
                f"A materialização {materialisation_id} já foi desfeita em {entry.undone_at:%d/%m/%Y %H:%M}."
            )

        created_ids = [node["description_id"] for node in entry.created_nodes]
        known = set(entry.previous_state)
        for parent_id, children in self.repo.children_of_nodes(created_ids).items():
            unknown = [child for child in children if child not in known]
            if unknown:
                raise InvalidHierarchyPlanError(
                    f"O nó {parent_id} recebeu descrições depois desta materialização ({len(unknown)}): "
                    "desfazer agora as desligaria. Desfaça primeiro o que as colocou lá."
                )

        self.repo.restore_state(entry.previous_state)
        self.repo.delete_created_nodes(created_ids)

        # The rungs that pointed at a node that no longer exists have to go back to "not
        # materialised", or the next apply would try to attach descriptions to a deleted row.
        deleted = set(created_ids)
        for plan in self.repo.all_plans().values():
            if plan.materialised_description_id in deleted:
                plan.materialised_description_id = None

        entry.undone_at = datetime.now(UTC)
        entry.undone_by = undone_by
        self.repo.db.flush()
        return self._to_log_dto(entry)

    # =========================================================================
    # The planner
    # =========================================================================
    def _plan(self) -> _Plan:
        plans = self.repo.all_plans()
        collapse_map = {code: plan.collapse_into_code for code, plan in plans.items() if plan.collapse_into_code}
        survivors = {
            code: plan
            for code, plan in plans.items()
            if plan.status == "APPROVED" and collapse_chain(code, collapse_map) == code
        }

        levels = {level.level_id: level.name for level in self.catalog.list_levels()}
        plan = _Plan()

        # Every code of the catalogue knows which approved rung it ends on — or that it ends on none.
        for code in plans:
            resolved = resolve_rung(code, collapse_map, survivors)
            plan.rung_map[code] = resolved or ""

        for code, stored in sorted(survivors.items()):
            if stored.materialised_description_id:
                action, node_id, node_path = ACTION_ALREADY, stored.materialised_description_id, None
            elif stored.existing_description_id:
                action, node_id, node_path = ACTION_ADOPT, stored.existing_description_id, None
            else:
                action, node_id, node_path = ACTION_CREATE, None, None

            parent_code = resolve_rung(parent_rung_code(code) or "", collapse_map, survivors)
            plan.rungs.append(
                _Rung(
                    code=code,
                    action=action,
                    node_id=node_id,
                    node_path=node_path,
                    parent_code=parent_code,
                    level_id=stored.level_id,
                    level_name=levels.get(stored.level_id) if stored.level_id is not None else None,
                    title=stored.title,
                    reference_code=stored.reference_code,
                    rooted_early=parent_code is None and self._has_unapproved_ancestor(code, plans, survivors),
                )
            )
            plan.node_parents[code] = parent_code

        # The path of an adopted node is the one it already has; a created one is its own id.
        # Read in one query rather than one per node: the alternative is a hidden N+1 on a screen
        # that is already doing a lot.
        adopted_state = self.repo.capture_state([rung.node_id for rung in plan.rungs if rung.node_id])
        for rung in plan.rungs:
            if rung.node_id and rung.node_id in adopted_state:
                rung.node_path = adopted_state[rung.node_id]["path"]

        node_by_code = {rung.code: rung for rung in plan.rungs}
        observations = self.repo.stream_code_observations()
        for observation in observations:
            rung_code = self._rung_of(observation)
            if rung_code is None:
                plan.orphan_ids.append(observation.description_id)
                continue
            target = resolve_rung(rung_code, collapse_map, survivors)
            if target is None:
                plan.orphan_ids.append(observation.description_id)
                continue

            rung = node_by_code[target]
            # A description that IS the adopted node is not a child of itself.
            if rung.node_id == observation.description_id:
                continue

            if self._is_placed(observation, rung):
                plan.documents_already_placed += 1
                continue

            plan.document_targets.setdefault(target, []).append(observation.description_id)

        return plan

    @staticmethod
    def _rung_of(observation: CodeObservation) -> str | None:
        sliced = slice_reference_code(observation.reference_code)
        if not sliced.structural:
            return None
        return normalize_reference_code(sliced.structural_code)

    @staticmethod
    def _is_placed(observation: CodeObservation, rung: _Rung) -> bool:
        """
        Whether the description is already hanging exactly where the decision puts it.

        Compared on the pair (parent, path) because a row can have the right parent and a stale
        path — the divergence the diagnostics exist to catch — and that still has to be repaired.
        """
        if rung.node_id is None or observation.parent_id != rung.node_id:
            return False
        expected = HierarchyMaterialisationService._child_path(rung.node_path, observation.description_id)
        return observation.path == expected

    @staticmethod
    def _child_path(parent_path: str | None, description_id: str) -> str:
        return description_id if not parent_path else f"{parent_path}.{description_id}"

    @staticmethod
    def _has_unapproved_ancestor(code: str, plans: dict, survivors: dict) -> bool:
        """True when a rung above this one is proposed but not approved, so the node sits early."""
        tokens = code.split(" ")
        for size in range(len(tokens) - 1, 1, -1):
            ancestor = " ".join(tokens[:size])
            if ancestor in plans and ancestor not in survivors:
                return True
        return False

    def _items(self, plan: _Plan, limit: int) -> list[HierarchyMaterialisationItem]:
        return [
            HierarchyMaterialisationItem(
                code=rung.code,
                action=rung.action,
                node_description_id=rung.node_id,
                parent_code=rung.parent_code,
                level=rung.level_name,
                title=rung.title,
                document_count=len(plan.document_targets.get(rung.code, [])),
                sample_description_ids=plan.document_targets.get(rung.code, [])[:5],
                rooted_early=rung.rooted_early,
            )
            for rung in plan.rungs[:limit]
        ]

    # =========================================================================
    # Helpers
    # =========================================================================
    def _proposal_service(self) -> HierarchyProposalService:
        if self._proposal is None:
            self._proposal = HierarchyProposalService(self.repo, self.catalog)
        return self._proposal

    @staticmethod
    def _to_dto(plan: ArchiveHierarchyNodePlan, levels: dict[int, str]) -> HierarchyNodePlanDTO:
        return HierarchyNodePlanDTO(
            plan_id=plan.plan_id,
            code=plan.code,
            depth=plan.depth,
            parent_code=plan.parent_code,
            document_count=plan.document_count,
            declared_levels=list(plan.declared_levels or []),
            flags=list(plan.flags or []),
            sample_description_ids=list(plan.sample_description_ids or []),
            existing_description_id=plan.existing_description_id,
            level_id=plan.level_id,
            level=levels.get(plan.level_id) if plan.level_id else None,
            title=plan.title,
            reference_code=plan.reference_code,
            status=plan.status,
            collapse_into_code=plan.collapse_into_code,
            decided_by=plan.decided_by,
            decided_at=plan.decided_at,
            decision_note=plan.decision_note,
            materialised_description_id=plan.materialised_description_id,
        )

    @staticmethod
    def _to_log_dto(entry: ArchiveHierarchyMaterialisationLog) -> HierarchyMaterialisationLogDTO:
        return HierarchyMaterialisationLogDTO(
            materialisation_id=entry.materialisation_id,
            created_nodes=list(entry.created_nodes or []),
            rung_map=dict(entry.rung_map or {}),
            changed_rows=len(entry.previous_state or {}),
            changed_by=entry.changed_by,
            changed_at=entry.changed_at,
            note=entry.note,
            undone_at=entry.undone_at,
            undone_by=entry.undone_by,
        )
