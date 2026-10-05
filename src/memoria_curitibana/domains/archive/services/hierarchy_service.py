"""Tree use cases: navigation, creation, reparent and diagnosis (Fase 2.5, H2)."""

from typing import Any

from memoria_curitibana.domains.archive.domain.hierarchy import (
    HierarchyIssue,
    NodeShape,
    build_path,
    dominant_ordinal_by_depth,
    validate_assignment,
)
from memoria_curitibana.domains.archive.domain.hierarchy_code import slice_reference_code
from memoria_curitibana.domains.archive.exceptions import (
    HierarchyNodeNotFoundError,
    InvalidHierarchyMoveError,
)
from memoria_curitibana.domains.archive.models import ArchiveDocument
from memoria_curitibana.domains.archive.repository.hierarchy_repo import (
    CodeObservation,
    HierarchyRepository,
)
from memoria_curitibana.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    CreateHierarchyNodeCommand,
    HierarchyDiagnosticListResponse,
    HierarchyDiagnosticSummary,
    HierarchyNodeDetail,
    HierarchyNodeSummary,
    HierarchyTreeResponse,
    MoveNodeCommand,
)

#: Issues the diagnostics endpoint knows how to produce. ``NEAR_DUPLICATE_NODE`` is deliberately
#: absent: it is a statement about codes the tree does *not* contain yet, so it is produced by the
#: proposal, where the codes are being read, and not here.
DIAGNOSTIC_ISSUES: tuple[str, ...] = (
    str(HierarchyIssue.ORPHAN),
    str(HierarchyIssue.DOSSIER_WITHOUT_PARENT),
    str(HierarchyIssue.UNKNOWN_LEVEL),
    str(HierarchyIssue.PATH_DIVERGENCE),
    str(HierarchyIssue.LEVEL_DEPTH_MISMATCH),
)


class HierarchyService:
    """
    Reads the arrangement, moves nodes and diagnoses the tree.

    A move is a curation act: it validates the rules of the ladder, rewrites the materialised path
    of the whole subtree in one statement and records the before/after in the review history. It
    deliberately does **not** set ``HUMAN_APPROVED``: hierarchy is arrangement, not content, and no
    AI worker writes ``parent_id``/``level_id``/``path``, so there is nothing for the lock to
    protect — while locking would freeze the enrichment of a fund for a decision about its place.
    """

    def __init__(self, repo: HierarchyRepository, catalog: LevelCatalogRepository) -> None:
        self.repo = repo
        self.catalog = catalog

    # =========================================================================
    # Navigation
    # =========================================================================
    def tree(
        self,
        root_id: str | None,
        max_depth: int | None,
        limit: int,
        offset: int,
    ) -> HierarchyTreeResponse:
        root_path = None
        if root_id is not None:
            root = self.repo.get_node(root_id)
            if root is None:
                raise HierarchyNodeNotFoundError(f"Descrição '{root_id}' não encontrada no acervo.")
            root_path = root.path

        nodes, total = self.repo.list_subtree(root_path, max_depth, limit, offset)
        counts = self.repo.children_counts([node.description_id for node in nodes])
        return HierarchyTreeResponse(
            root_id=root_id,
            total=total,
            items=[self.repo.to_summary(node, counts.get(node.description_id, 0)) for node in nodes],
        )

    def children(self, description_id: str) -> list[HierarchyNodeSummary]:
        self._require_node(description_id)
        nodes = self.repo.list_children(description_id)
        counts = self.repo.children_counts([node.description_id for node in nodes])
        return [self.repo.to_summary(node, counts.get(node.description_id, 0)) for node in nodes]

    def node(self, description_id: str) -> HierarchyNodeDetail:
        """
        The node, its branch and its children, in one read.

        The three lookups are the ones the individual edit already makes separately; putting them
        behind one route keeps the screen from issuing three round trips to render one card.
        """
        node = self._require_node(description_id)
        ancestors = self.repo.list_ancestors(node.path)
        children = self.repo.list_children(description_id)
        counts = self.repo.children_counts([node.description_id, *[child.description_id for child in children]])
        return HierarchyNodeDetail(
            node=self.repo.to_summary(node, counts.get(node.description_id, 0)),
            ancestors=[self.repo.to_summary(ancestor) for ancestor in ancestors],
            children=[self.repo.to_summary(child, counts.get(child.description_id, 0)) for child in children],
        )

    def ancestors(self, description_id: str) -> list[HierarchyNodeSummary]:
        """Ancestors, root first. The node itself is not included."""
        node = self._require_node(description_id)
        return [self.repo.to_summary(ancestor) for ancestor in self.repo.list_ancestors(node.path)]

    # =========================================================================
    # Writes
    # =========================================================================
    def create_node(self, command: CreateHierarchyNodeCommand) -> HierarchyNodeSummary:
        """
        Materialises a rung the source never declared.

        The rules are validated against the parent exactly like a move, so an Item cannot be given
        a child and a Dossiê cannot be created at the root by accident: the same function decides
        both paths.
        """
        parent = None
        if command.parent_id is not None:
            parent = self._require_node(command.parent_id)

        rules = self.catalog.rules_by_id()
        child_level = rules.get(command.level_id) if command.level_id is not None else None
        parent_shape = self._shape(parent, rules) if parent else None

        violations = validate_assignment(
            description_id="",
            node_path="",
            new_parent=parent_shape,
            child_level=child_level,
        )
        if violations:
            raise InvalidHierarchyMoveError(self._explain(violations))

        node = self.repo.create_node(command, parent)
        return self.repo.to_summary(node)

    def move(self, description_id: str, command: MoveNodeCommand) -> HierarchyNodeSummary:
        """
        Reparents and/or re-levels a node, rewriting its subtree's path.

        ``new_parent_id`` is explicit even when unchanged: the endpoint states where the node goes,
        and ``None`` means "to the root". Omitted ``level_id`` keeps the current rung.
        """
        node = self._require_node(description_id)
        rules = self.catalog.rules_by_id()

        level_id = command.level_id if command.level_id is not None else node.level_id
        child_level = rules.get(level_id) if level_id is not None else None

        new_parent: ArchiveDocument | None = None
        if command.new_parent_id is not None:
            new_parent = self._require_node(command.new_parent_id)

        violations = validate_assignment(
            description_id=node.description_id,
            node_path=node.path,
            new_parent=self._shape(new_parent, rules) if new_parent else None,
            child_level=child_level,
        )
        if violations:
            raise InvalidHierarchyMoveError(self._explain(violations))

        new_path = build_path(new_parent.path if new_parent else None, node.description_id)
        old_path = node.path
        old_parent_id = node.parent_id
        old_level_id = node.level_id

        self.repo.reparent(node, new_parent, new_path, command.level_id)

        changes: dict[str, Any] = {}
        if old_parent_id != node.parent_id:
            changes["parent_id"] = {"old": old_parent_id, "new": node.parent_id}
        if old_level_id != node.level_id:
            changes["level_id"] = {"old": old_level_id, "new": node.level_id}
        if changes:
            # The path is derived, but it is recorded too: it is what a reader needs to see which
            # subtree the move took with it.
            changes["path"] = {"old": old_path, "new": new_path}
            self.repo.record_revision(node.description_id, changes, command.changed_by, command.note)

        moved = self._require_node(description_id)
        return self.repo.to_summary(moved)

    # =========================================================================
    # Diagnostics
    # =========================================================================
    def diagnostics(self, issue: str, limit: int, offset: int) -> HierarchyDiagnosticListResponse:
        if issue not in DIAGNOSTIC_ISSUES:
            raise InvalidHierarchyMoveError(
                f"Diagnóstico '{issue}' não existe. Válidos: {', '.join(DIAGNOSTIC_ISSUES)}."
            )

        if issue == str(HierarchyIssue.ORPHAN):
            items, total = self.repo.find_orphans(limit, offset)
        elif issue == str(HierarchyIssue.DOSSIER_WITHOUT_PARENT):
            items, total = self.repo.find_dossiers_without_parent(limit, offset)
        elif issue == str(HierarchyIssue.UNKNOWN_LEVEL):
            items, total = self.repo.find_unknown_levels(limit, offset)
        elif issue == str(HierarchyIssue.PATH_DIVERGENCE):
            items, total = self.repo.find_path_divergences(limit, offset)
        else:
            items, total = self._level_depth_mismatches(limit, offset)

        return HierarchyDiagnosticListResponse(issue=issue, total=total, limit=limit, offset=offset, items=items)

    def diagnostic_summary(self) -> HierarchyDiagnosticSummary:
        """
        The count of every issue, for the section headers of the diagnosis screen.

        Computed by the same code path that serves each page, with ``limit=0``: the screen then
        cannot show a header that disagrees with the list it opens, which is the failure mode of
        counting the sections with a second query written by hand.
        """
        counts = {issue: self.diagnostics(issue, limit=0, offset=0).total for issue in DIAGNOSTIC_ISSUES}
        return HierarchyDiagnosticSummary(counts=counts)

    def _level_depth_mismatches(self, limit: int, offset: int):
        """
        Declared levels that disagree with the level the collection uses at that code depth.

        The norm is **learned** from the collection (``dominant_ordinal_by_depth``) instead of
        hardcoded, because the measurement says no depth-to-level mapping exists to hardcode: five
        tokens hold Items, a Série and a Seção. A tie yields no norm, so the two Seções and two
        Séries at four tokens flag nothing — only a level that is a minority at its depth does.
        """
        observations = self.repo.stream_code_observations()
        norms = dominant_ordinal_by_depth(
            (len(slice_reference_code(obs.reference_code).structural), obs.level_ordinal)
            for obs in observations
            if obs.level_ordinal is not None
        )

        mismatched: list[tuple[CodeObservation, int]] = []
        for obs in observations:
            if obs.level_ordinal is None:
                continue
            depth = len(slice_reference_code(obs.reference_code).structural)
            expected = norms.get(depth)
            if expected is not None and expected != obs.level_ordinal:
                mismatched.append((obs, expected))

        total = len(mismatched)
        page = mismatched[offset : offset + limit]
        items = [
            self.repo.to_diagnostic(
                self._observation_as_node(obs),
                str(HierarchyIssue.LEVEL_DEPTH_MISMATCH),
                detail={
                    "code_depth": len(slice_reference_code(obs.reference_code).structural),
                    "expected_ordinal": expected,
                    "declared_ordinal": obs.level_ordinal,
                },
                level_name=obs.level_name,
            )
            for obs, expected in page
        ]
        return items, total

    # =========================================================================
    # Helpers
    # =========================================================================
    def _require_node(self, description_id: str) -> ArchiveDocument:
        node = self.repo.get_node(description_id)
        if node is None:
            raise HierarchyNodeNotFoundError(f"Descrição '{description_id}' não encontrada no acervo.")
        return node

    @staticmethod
    def _shape(node: ArchiveDocument | None, rules: dict) -> NodeShape | None:
        if node is None:
            return None
        return NodeShape(
            description_id=node.description_id,
            parent_id=node.parent_id,
            path=node.path,
            level=rules.get(node.level_id),
        )

    @staticmethod
    def _observation_as_node(obs: CodeObservation) -> ArchiveDocument:
        """
        Wraps an observation so the diagnostic builder can format it.

        Built detached and never added to the session: the diagnostics read a projection, and
        adding these instances would make the session flush them as updates.
        """
        return ArchiveDocument(
            description_id=obs.description_id,
            original_title=obs.title or "",
            reference_code=obs.reference_code,
            level_id=obs.level_id,
            path=obs.path,
            staging_content_hash="projection",
        )

    @staticmethod
    def _explain(violations: list) -> str:
        messages = {
            "SELF_PARENT": "Uma descrição não pode ser pai de si mesma.",
            "CYCLE": "A unidade superior escolhida está dentro da própria subárvore: isso criaria um ciclo.",
            "LEVEL_NOT_ALLOWED_AS_CHILD": "O nível do filho precisa ser posterior ao nível do pai na escada.",
            "PARENT_ALLOWS_NO_CHILDREN": "O nível da unidade superior escolhida não admite filhos.",
            "REQUIRED_LEVEL_WITHOUT_PARENT": "Este nível não pode ficar na raiz: escolha uma unidade superior.",
        }
        return " ".join(messages.get(str(violation), str(violation)) for violation in violations)
