"""Persistence of the arrangement tree (Fase 2.5, H2).

Kept apart from ``DocumentRepository`` for the same reason the tree is a different concern from
the document: this repository owns the columns only curation writes (``parent_id``, ``path``)
and the queries the navigation makes, while ``DocumentRepository`` keeps owning the descriptive
content and the search.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.orm import Session, aliased, selectinload
from sqlalchemy.sql.elements import ColumnElement

from scrinalia.domains.archive.domain.hierarchy import (
    PATH_SEPARATOR,
    HierarchyIssue,
    PlanStatus,
    build_path,
)
from scrinalia.domains.archive.domain.normalization import LIKE_ESCAPE, escape_like
from scrinalia.domains.archive.models import (
    ArchiveDescriptionLevel,
    ArchiveDocument,
    ArchiveDocumentRevision,
    ArchiveHierarchyMaterialisationLog,
    ArchiveHierarchyNodePlan,
    ArchiveReviewStatus,
)
from scrinalia.domains.archive.schemas.hierarchy_schema import (
    CreateHierarchyNodeCommand,
    HierarchyDiagnostic,
    HierarchyNodeSummary,
)

#: Marks a description that curation created and the source never delivered (a fund, a section,
#: a series). ``staging_content_hash`` is ``NOT NULL`` because it is the staging->archive CDC
#: key, so an arrangement node carries an explicit non-hash sentinel instead of a fake one.
CURATION_CONTENT_HASH = "curation:created-node"

#: Prefix of the generated primary key of a created node, so one is recognisable on sight.
CURATION_ID_PREFIX = "node_"

#: The code-derived diagnostics classify every description in memory (the slicer cannot be
#: expressed in SQL). The collection is 3.6k descriptions, where this is milliseconds; the cap
#: exists so a pathological collection fails loudly instead of exhausting memory.
CODE_DIAGNOSTIC_SCAN_LIMIT = 200_000


@dataclass(frozen=True)
class CodeObservation:
    """
    Everything the code-derived diagnostics and the materialisation need about one description.

    ``parent_id`` travels with the row so the dry run can tell "this description has to move" from
    "this description is already there": without it the preview would report the whole collection
    as changed on every run, which is the kind of number a curator stops reading.
    """

    description_id: str
    reference_code: str
    level_id: int | None
    level_ordinal: int | None
    level_name: str | None
    title: str | None
    path: str
    parent_id: str | None = None


class HierarchyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # =========================================================================
    # Nodes
    # =========================================================================
    def get_node(self, description_id: str) -> ArchiveDocument | None:
        """The managed entity, with its level loaded so ``level`` can be read without a query."""
        stmt = (
            select(ArchiveDocument)
            .where(ArchiveDocument.description_id == description_id)
            .options(selectinload(ArchiveDocument.level_ref))
        )
        return self.db.scalars(stmt).first()

    def get_nodes(self, description_ids: list[str]) -> dict[str, ArchiveDocument]:
        if not description_ids:
            return {}
        stmt = (
            select(ArchiveDocument)
            .where(ArchiveDocument.description_id.in_(description_ids))
            .options(selectinload(ArchiveDocument.level_ref))
        )
        return {node.description_id: node for node in self.db.scalars(stmt).all()}

    def create_node(self, command: CreateHierarchyNodeCommand, parent: ArchiveDocument | None) -> ArchiveDocument:
        """
        Inserts an arrangement node the source never delivered.

        It is born ``HUMAN_APPROVED``: a person created it, and the AI has nothing to enrich on a
        rung that exists only to hold others. Its path comes from the parent's, which is the same
        rule every other node follows.
        """
        description_id = f"{CURATION_ID_PREFIX}{uuid.uuid4().hex[:30]}"
        node = ArchiveDocument(
            description_id=description_id,
            original_title=command.title,
            reference_code=command.reference_code,
            scope_content=command.scope_content,
            staging_content_hash=CURATION_CONTENT_HASH,
            level_id=command.level_id,
            parent_id=parent.description_id if parent else None,
            path=build_path(parent.path if parent else None, description_id),
            review_status=ArchiveReviewStatus.HUMAN_APPROVED,
            execution_log={},
        )
        self.db.add(node)
        self.db.flush()
        return node

    # =========================================================================
    # The materialised path
    # =========================================================================
    def reparent(
        self,
        node: ArchiveDocument,
        new_parent: ArchiveDocument | None,
        new_path: str,
        level_id: int | None,
    ) -> int:
        """
        Moves the node and rewrites the path of its whole subtree in one statement.

        The order matters: the node moves first (with a flush, so its own row stops matching the
        old prefix), then the descendants are rewritten from the old prefix to the new one. The
        other way round would rewrite the node twice.

        The rewrite uses ``substr(path, length(old) + 1)`` rather than walking the subtree: one
        round trip for any depth, and it cannot leave a node behind.
        """
        old_path = node.path
        node.parent_id = new_parent.description_id if new_parent else None
        if level_id is not None:
            node.level_id = level_id
        node.path = new_path
        self.db.flush()

        if old_path == new_path:
            return 0

        result = self.db.execute(
            update(ArchiveDocument)
            .where(ArchiveDocument.path.like(f"{old_path}.%"))
            .values(path=func.concat(new_path, func.substr(ArchiveDocument.path, len(old_path) + 1)))
            .execution_options(synchronize_session=False)
        )
        # The descendants were never loaded, but any stale instance must not survive the move.
        self.db.expire_all()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def record_revision(
        self,
        description_id: str,
        changes: dict,
        changed_by: str | None,
        note: str | None,
    ) -> None:
        """
        Appends the move to the same audit trail every other human edit uses.

        The hierarchy shares ``archive_document_revisions`` with the descriptive edits on purpose:
        "who moved this, from where to where" is a curation decision and belongs in one history,
        not in a second ledger that a reader would have to know about.
        """
        self.db.add(
            ArchiveDocumentRevision(
                description_id=description_id,
                changed_by=changed_by,
                changes=changes,
                note=note,
            )
        )
        self.db.flush()

    # =========================================================================
    # Navigation reads
    # =========================================================================
    def list_subtree(
        self,
        root_path: str | None,
        max_depth: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ArchiveDocument], int]:
        """
        The subtree of one path, ordered by ``path``, or the whole forest when it is ``None``.

        The subtree predicate is a single indexed ``LIKE 'path.%'``: that is the whole reason
        ``path`` is materialised, and the index is declared ``text_pattern_ops`` so PostgreSQL
        can actually use it under this database's collation.
        """
        stmt = select(ArchiveDocument).options(selectinload(ArchiveDocument.level_ref))

        if root_path:
            stmt = stmt.where(
                or_(
                    ArchiveDocument.path == root_path,
                    ArchiveDocument.path.like(f"{root_path}.%"),
                )
            )
            if max_depth is not None:
                # Depth is the number of separators; the comparison is relative to the root, so
                # ``max_depth=1`` means "the root and its children".
                root_depth = root_path.count(".")
                path_depth = func.length(ArchiveDocument.path) - func.length(
                    func.replace(ArchiveDocument.path, ".", "")
                )
                stmt = stmt.where(path_depth - root_depth <= max_depth)
        elif max_depth is not None:
            # The forest has no root to measure against, so the depth is absolute: ``max_depth=0``
            # answers the roots alone. A navigation needs exactly that before it expands anything,
            # and without it the only way to list the roots is to page the whole collection and
            # filter in the application — which reads thousands of rows to draw a dozen.
            path_depth = func.length(ArchiveDocument.path) - func.length(func.replace(ArchiveDocument.path, ".", ""))
            stmt = stmt.where(path_depth <= max_depth)

        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        page = stmt.order_by(ArchiveDocument.path).limit(limit).offset(offset)
        return list(self.db.scalars(page).all()), total

    def get_path(self, description_id: str) -> str | None:
        return self.db.scalar(select(ArchiveDocument.path).where(ArchiveDocument.description_id == description_id))

    def list_ancestors(self, path: str) -> list[ArchiveDocument]:
        """
        The ancestors of a node, root first, read from the materialised path.

        One ``IN`` over the ids embedded in the path instead of a recursive walk per level.
        """
        ancestor_ids = path.split(".")[:-1]
        if not ancestor_ids:
            return []
        nodes = self.get_nodes(ancestor_ids)
        return [nodes[node_id] for node_id in ancestor_ids if node_id in nodes]

    def list_children(self, description_id: str) -> list[ArchiveDocument]:
        stmt = (
            select(ArchiveDocument)
            .where(ArchiveDocument.parent_id == description_id)
            .options(selectinload(ArchiveDocument.level_ref))
            .order_by(ArchiveDocument.path)
        )
        return list(self.db.scalars(stmt).all())

    def children_counts(self, description_ids: list[str]) -> dict[str, int]:
        if not description_ids:
            return {}
        rows = self.db.execute(
            select(ArchiveDocument.parent_id, func.count())
            .where(ArchiveDocument.parent_id.in_(description_ids))
            .group_by(ArchiveDocument.parent_id)
        ).all()
        return {str(parent_id): int(count) for parent_id, count in rows}

    @staticmethod
    def to_summary(node: ArchiveDocument, children_count: int = 0) -> HierarchyNodeSummary:
        level = node.level_ref
        return HierarchyNodeSummary(
            description_id=node.description_id,
            reference_code=node.reference_code,
            title=node.final_title or node.original_title,
            level_id=node.level_id,
            level=node.level,
            parent_id=node.parent_id,
            path=node.path,
            children_count=children_count,
            is_orphan=node.parent_id is None and level is not None and level.requires_parent,
        )

    @staticmethod
    def to_diagnostic(
        node: ArchiveDocument,
        issue: str,
        detail: dict | None = None,
        level_name: str | None = None,
    ) -> HierarchyDiagnostic:
        """
        Builds the diagnostic payload.

        ``level_name`` exists for the code-derived diagnostics, which classify a detached
        projection: the relationship is not loaded there, so the name has to travel with the row
        instead of being read through ``node.level``.
        """
        return HierarchyDiagnostic(
            description_id=node.description_id,
            issue=issue,
            reference_code=node.reference_code,
            title=node.final_title or node.original_title,
            level_id=node.level_id,
            level=node.level if level_name is None else level_name,
            path=node.path,
            detail=detail or {},
        )

    # =========================================================================
    # Diagnostics
    # =========================================================================
    def find_orphans(self, limit: int, offset: int) -> tuple[list[HierarchyDiagnostic], int]:
        """
        Descriptions without a parent whose level demands one, plus the unclassified ones.

        Both are reported under one code because they call for the same curator action ("choose a
        parent"). A row is a genuine orphan when its level requires a parent; a description with
        no level at all is listed too, since it cannot be judged and must still be looked at.
        """
        condition = and_(
            ArchiveDocument.parent_id.is_(None),
            or_(
                ArchiveDocument.level_id.is_(None),
                ArchiveDocument.level_ref.has(ArchiveDescriptionLevel.requires_parent.is_(True)),  # type: ignore[attr-defined]
            ),
        )
        return self._diagnostics_page(condition, str(HierarchyIssue.ORPHAN), limit, offset)

    def find_dossiers_without_parent(self, limit: int, offset: int) -> tuple[list[HierarchyDiagnostic], int]:
        """The narrower, named case: an obligatory level (Dossiê) sitting at the root."""
        condition = and_(
            ArchiveDocument.parent_id.is_(None),
            ArchiveDocument.level_ref.has(ArchiveDescriptionLevel.code == "dossie"),  # type: ignore[attr-defined]
        )
        return self._diagnostics_page(condition, str(HierarchyIssue.DOSSIER_WITHOUT_PARENT), limit, offset)

    def find_unknown_levels(self, limit: int, offset: int) -> tuple[list[HierarchyDiagnostic], int]:
        """Descriptions the catalogue could not classify: the transfer never fails on them."""
        return self._diagnostics_page(
            ArchiveDocument.level_id.is_(None), str(HierarchyIssue.UNKNOWN_LEVEL), limit, offset
        )

    def find_path_divergences(self, limit: int, offset: int) -> tuple[list[HierarchyDiagnostic], int]:
        """
        Rows whose materialised path disagrees with their parent's — the invariant broken.

        Should always be empty: the service is the only writer and it rewrites the subtree in the
        same transaction. It is queried anyway, because "should be empty" is exactly the kind of
        claim a health check exists to falsify.

        The **expected** path travels in ``detail`` with the stored one. A divergence is the one
        diagnostic whose evidence is a comparison, and a screen that shows only "this row is wrong"
        would be asking the archivist to take the claim on faith.
        """
        parent = aliased(ArchiveDocument)
        condition = or_(
            and_(
                ArchiveDocument.parent_id.is_not(None),
                ArchiveDocument.path != func.concat(parent.path, ".", ArchiveDocument.description_id),
            ),
            and_(
                ArchiveDocument.parent_id.is_(None),
                ArchiveDocument.path != ArchiveDocument.description_id,
            ),
        )
        broken = (
            select(ArchiveDocument.description_id)
            .outerjoin(parent, parent.description_id == ArchiveDocument.parent_id)
            .where(condition)
        )
        total = int(self.db.scalar(select(func.count()).select_from(broken.subquery())) or 0)
        if total == 0:
            # The normal state of the collection: the invariant holds and there is nothing to read.
            return [], 0

        expected_path = case(
            (ArchiveDocument.parent_id.is_(None), ArchiveDocument.description_id),
            else_=func.concat(parent.path, ".", ArchiveDocument.description_id),
        )
        expected_by_id = {
            str(description_id): str(esperado)
            for description_id, esperado in self.db.execute(
                select(ArchiveDocument.description_id, expected_path)
                .outerjoin(parent, parent.description_id == ArchiveDocument.parent_id)
                .where(condition)
            ).all()
        }
        rows = self.db.scalars(
            select(ArchiveDocument)
            .where(ArchiveDocument.description_id.in_(broken))
            .options(selectinload(ArchiveDocument.level_ref))
            .order_by(ArchiveDocument.description_id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [
            self.to_diagnostic(
                node,
                str(HierarchyIssue.PATH_DIVERGENCE),
                detail={"path": node.path, "expected_path": expected_by_id.get(node.description_id)},
            )
            for node in rows
        ], total

    def stream_code_observations(self) -> list[CodeObservation]:
        """
        Every description that carries a reference code, for the code-derived diagnostics.

        The structural depth of a code is read by ``domain.hierarchy_code``, which cannot be
        expressed in SQL without reimplementing it; so the code-derived diagnostics are classified
        in the domain over this bounded read. At 3.6k descriptions that is milliseconds, and the
        cap makes a pathological collection fail loudly instead of exhausting memory.
        """
        catalogue = {
            level.level_id: (level.ordinal, level.name)
            for level in self.db.scalars(select(ArchiveDescriptionLevel)).all()
        }
        stmt = (
            select(
                ArchiveDocument.description_id,
                ArchiveDocument.reference_code,
                ArchiveDocument.level_id,
                ArchiveDocument.path,
                ArchiveDocument.original_title,
                ArchiveDocument.final_title,
                ArchiveDocument.parent_id,
            )
            .where(ArchiveDocument.reference_code.is_not(None))
            .order_by(ArchiveDocument.description_id)
            .limit(CODE_DIAGNOSTIC_SCAN_LIMIT)
        )

        observations: list[CodeObservation] = []
        for row in self.db.execute(stmt):
            description_id, reference_code, level_id, path, original_title, final_title, parent_id = row
            ordinal, name = catalogue.get(level_id, (None, None))
            observations.append(
                CodeObservation(
                    description_id=description_id,
                    reference_code=reference_code,
                    level_id=level_id,
                    level_ordinal=ordinal,
                    level_name=name,
                    title=final_title or original_title,
                    path=path,
                    parent_id=parent_id,
                )
            )
        return observations

    def _diagnostics_page(
        self, condition: ColumnElement[bool], issue: str, limit: int, offset: int
    ) -> tuple[list[HierarchyDiagnostic], int]:
        base = select(ArchiveDocument).where(condition).options(selectinload(ArchiveDocument.level_ref))
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = self.db.scalars(base.order_by(ArchiveDocument.description_id).limit(limit).offset(offset)).all()
        return [self.to_diagnostic(node, issue) for node in rows], total

    # =========================================================================
    # H4 — The plan catalogue and the materialisation ledger
    # =========================================================================
    def list_plans(self, status: str | None, limit: int, offset: int) -> tuple[list[ArchiveHierarchyNodePlan], int]:
        base = select(ArchiveHierarchyNodePlan)
        if status is not None:
            base = base.where(ArchiveHierarchyNodePlan.status == status)
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = self.db.scalars(base.order_by(ArchiveHierarchyNodePlan.code).limit(limit).offset(offset)).all()
        return list(rows), total

    def all_plans(self) -> dict[str, ArchiveHierarchyNodePlan]:
        return {plan.code: plan for plan in self.db.scalars(select(ArchiveHierarchyNodePlan)).all()}

    def get_plan(self, plan_id: int) -> ArchiveHierarchyNodePlan | None:
        return self.db.get(ArchiveHierarchyNodePlan, plan_id)

    def get_plan_by_code(self, code: str) -> ArchiveHierarchyNodePlan | None:
        return self.db.scalars(select(ArchiveHierarchyNodePlan).where(ArchiveHierarchyNodePlan.code == code)).first()

    def upsert_plan(self, code: str, evidence: dict[str, Any]) -> tuple[ArchiveHierarchyNodePlan, bool, bool]:
        """
        Writes one suggested rung and reports ``(plan, created, refreshed)``.

        Refreshing the evidence of a row a human already decided would let a re-run quietly rewrite
        the numbers the decision was taken on, so the refresh is confined to ``SUGGESTED`` rows —
        the same rule the tag-merge catalogue follows.
        """
        plan = self.get_plan_by_code(code)
        if plan is None:
            plan = ArchiveHierarchyNodePlan(code=code, **evidence)
            self.db.add(plan)
            self.db.flush()
            return plan, True, False

        if plan.status != "SUGGESTED":
            return plan, False, False

        for field, value in evidence.items():
            setattr(plan, field, value)
        self.db.flush()
        return plan, False, True

    def count_plans(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(ArchiveHierarchyNodePlan)) or 0)

    def count_plans_by_status(self) -> dict[str, int]:
        """
        How many rungs sit on each verdict, with the zeroes present.

        One grouped query instead of one per status, and the statuses come from ``PlanStatus`` so a
        status the vocabulary knows but no row carries is reported as ``0`` rather than missing —
        the screen draws a progress bar over the whole catalogue, and a key that disappears at zero
        would move the denominator.
        """
        counts = {str(status): 0 for status in PlanStatus}
        rows = self.db.execute(
            select(ArchiveHierarchyNodePlan.status, func.count()).group_by(ArchiveHierarchyNodePlan.status)
        ).all()
        for status, total in rows:
            counts[str(status)] = int(total)
        return counts

    def capture_state(self, description_ids: list[str]) -> dict[str, Any]:
        """The exact ``(parent_id, path)`` every one of these rows has right now."""
        if not description_ids:
            return {}
        rows = self.db.execute(
            select(
                ArchiveDocument.description_id,
                ArchiveDocument.parent_id,
                ArchiveDocument.path,
            ).where(ArchiveDocument.description_id.in_(description_ids))
        ).all()
        return {str(row[0]): {"parent_id": row[1], "path": row[2]} for row in rows}

    def attach_group(self, description_ids: list[str], parent_id: str | None, parent_path: str | None) -> int:
        """
        Hangs a whole group under one parent in a single statement.

        The path is recomputed from the parent's rather than walked, and the group shares the same
        parent, so one rung costs one round trip — which is what makes attaching 3,602 descriptions
        a matter of seconds instead of a per-row loop.
        """
        if not description_ids:
            return 0
        path_expression = (
            ArchiveDocument.description_id
            if parent_path is None
            else func.concat(parent_path, PATH_SEPARATOR, ArchiveDocument.description_id)
        )
        result = self.db.execute(
            update(ArchiveDocument)
            .where(ArchiveDocument.description_id.in_(description_ids))
            .values(parent_id=parent_id, path=path_expression)
            .execution_options(synchronize_session=False)
        )
        self.db.expire_all()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def restore_state(self, previous_state: dict[str, Any]) -> int:
        """
        Puts every recorded row back exactly as it was, in one bulk statement.

        ``update(Model), [dicts]`` is SQLAlchemy's update-by-primary-key form: one executemany for
        the whole ledger instead of one statement per description.
        """
        if not previous_state:
            return 0
        payload = [
            {
                "description_id": description_id,
                "parent_id": state.get("parent_id"),
                "path": state.get("path"),
            }
            for description_id, state in previous_state.items()
        ]
        self.db.execute(update(ArchiveDocument), payload)
        self.db.expire_all()
        return len(payload)

    def delete_created_nodes(self, description_ids: list[str]) -> int:
        """
        Removes the descriptions a materialisation created.

        The self-reference is ``RESTRICT``, so the caller has to have restored the children first —
        the undo does exactly that, and this method is the last step, not the first.
        """
        if not description_ids:
            return 0
        result = self.db.execute(
            delete(ArchiveDocument)
            .where(ArchiveDocument.description_id.in_(description_ids))
            .execution_options(synchronize_session=False)
        )
        self.db.expire_all()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def children_of_nodes(self, description_ids: list[str]) -> dict[str, list[str]]:
        """Children of the given nodes, used by the undo to refuse a reversal it cannot do safely."""
        if not description_ids:
            return {}
        rows = self.db.execute(
            select(ArchiveDocument.parent_id, ArchiveDocument.description_id).where(
                ArchiveDocument.parent_id.in_(description_ids)
            )
        ).all()
        grouped: dict[str, list[str]] = {}
        for parent_id, child_id in rows:
            grouped.setdefault(str(parent_id), []).append(str(child_id))
        return grouped

    def create_materialisation_log(
        self,
        created_nodes: list[dict[str, Any]],
        rung_map: dict[str, Any],
        previous_state: dict[str, Any],
        changed_by: str | None,
        note: str | None,
    ) -> ArchiveHierarchyMaterialisationLog:
        entry = ArchiveHierarchyMaterialisationLog(
            created_nodes=created_nodes,
            rung_map=rung_map,
            previous_state=previous_state,
            changed_by=changed_by,
            note=note,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def get_materialisation_log(self, materialisation_id: int) -> ArchiveHierarchyMaterialisationLog | None:
        return self.db.get(ArchiveHierarchyMaterialisationLog, materialisation_id)

    def list_materialisation_logs(
        self, include_undone: bool, limit: int, offset: int, term: str | None = None
    ) -> tuple[list[ArchiveHierarchyMaterialisationLog], int]:
        """
        One page of the materialisation ledger, newest first.

        ``term`` matches the author and the note: a run is recognised by who ran it and why, and those
        are the two fields the ledger carries. ``escape_like`` keeps a ``%`` in the box a character.
        """
        base = select(ArchiveHierarchyMaterialisationLog)
        if not include_undone:
            base = base.where(ArchiveHierarchyMaterialisationLog.undone_at.is_(None))
        if term:
            pattern = f"%{escape_like(term)}%"
            base = base.where(
                or_(
                    ArchiveHierarchyMaterialisationLog.changed_by.ilike(pattern, escape=LIKE_ESCAPE),
                    ArchiveHierarchyMaterialisationLog.note.ilike(pattern, escape=LIKE_ESCAPE),
                )
            )
        total = int(self.db.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = self.db.scalars(
            base.order_by(ArchiveHierarchyMaterialisationLog.changed_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total
