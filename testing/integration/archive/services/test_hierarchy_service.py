"""
The tree against the real database: the materialised path, the guards and the diagnostics.

The invariant is the load-bearing assertion of this file. Every navigation query is a single
indexed ``path LIKE 'x.%'``, which is only correct while ``path == parent.path + "." + id`` — so a
subtree move is checked row by row, and the divergence diagnostic is exercised with a deliberately
broken row.
"""

import pytest
from sqlalchemy import select, text

from memoria_curitibana.domains.archive.domain.hierarchy import HierarchyIssue
from memoria_curitibana.domains.archive.exceptions import (
    HierarchyNodeNotFoundError,
    InvalidHierarchyMoveError,
)
from memoria_curitibana.domains.archive.models import ArchiveDocument, ArchiveDocumentRevision
from memoria_curitibana.domains.archive.repository.hierarchy_repo import HierarchyRepository
from memoria_curitibana.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from memoria_curitibana.domains.archive.schemas.hierarchy_schema import (
    CreateHierarchyNodeCommand,
    MoveNodeCommand,
)
from memoria_curitibana.domains.archive.services.hierarchy_service import HierarchyService


@pytest.fixture
def hierarchy(db_session):
    return HierarchyService(HierarchyRepository(db_session), LevelCatalogRepository(db_session))


@pytest.fixture
def nobrade(db_session, seed_nobrade_levels):
    """The seeded ladder keyed by code, so a test can name the rung it means."""
    return {level.code: level for level in seed_nobrade_levels()}


def _assert_invariant(db_session) -> None:
    """Every node's path equals its parent's plus its own id, and a root's is its own id."""
    broken = db_session.execute(
        text(
            """
            SELECT d.description_id, d.path
              FROM archive_documents d
              LEFT JOIN archive_documents p ON p.description_id = d.parent_id
             WHERE d.path <> coalesce(p.path || '.', '') || d.description_id
            """
        )
    ).all()
    assert broken == []


class TestTheMaterialisedPath:
    def test_a_created_node_is_a_root_by_default(self, db_session, hierarchy, nobrade):
        node = hierarchy.create_node(
            CreateHierarchyNodeCommand(reference_code="BR PRADAP", title="Acervo", level_id=nobrade["acervo"].level_id)
        )
        assert node.path == node.description_id
        assert node.parent_id is None
        _assert_invariant(db_session)

    def test_a_child_extends_its_parent(self, db_session, hierarchy, nobrade):
        root = hierarchy.create_node(
            CreateHierarchyNodeCommand(reference_code="BR PRADAP", title="Acervo", level_id=nobrade["acervo"].level_id)
        )
        fund = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP SMU",
                title="SMU",
                level_id=nobrade["fundo"].level_id,
                parent_id=root.description_id,
            )
        )
        assert fund.path == f"{root.path}.{fund.description_id}"
        _assert_invariant(db_session)
        assert [ancestor.description_id for ancestor in hierarchy.ancestors(fund.description_id)] == [
            root.description_id
        ]

    def test_moving_a_node_rewrites_the_whole_subtree_in_one_statement(self, db_session, hierarchy, nobrade):
        """
        The subtree move is the query that makes the materialised path worth its denormalisation.
        Every descendant has to follow, and the invariant is asserted after the move, not trusted.
        """
        root = hierarchy.create_node(
            CreateHierarchyNodeCommand(reference_code="BR PRADAP", title="Acervo", level_id=nobrade["acervo"].level_id)
        )
        fund_a = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP SMU",
                title="SMU",
                level_id=nobrade["fundo"].level_id,
                parent_id=root.description_id,
            )
        )
        fund_b = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP IPPUC",
                title="IPPUC",
                level_id=nobrade["fundo"].level_id,
                parent_id=root.description_id,
            )
        )
        series = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP SMU ED",
                title="Edificações",
                level_id=nobrade["secao"].level_id,
                parent_id=fund_a.description_id,
            )
        )
        leaf = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP SMU ED AL",
                title="Alvenaria",
                level_id=nobrade["serie"].level_id,
                parent_id=series.description_id,
            )
        )

        old_prefix = leaf.path
        hierarchy.move(
            series.description_id,
            MoveNodeCommand(new_parent_id=fund_b.description_id, changed_by="ana", note="Rearranjo"),
        )

        _assert_invariant(db_session)
        moved_leaf = hierarchy.tree(root_id=leaf.description_id, max_depth=None, limit=10, offset=0).items[0]
        assert moved_leaf.path == f"{fund_b.path}.{series.description_id}.{leaf.description_id}"
        assert moved_leaf.path != old_prefix

    def test_the_subtree_query_returns_the_root_and_its_descendants(self, db_session, hierarchy, nobrade):
        root = hierarchy.create_node(
            CreateHierarchyNodeCommand(reference_code="BR PRADAP", title="Acervo", level_id=nobrade["acervo"].level_id)
        )
        fund = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP SMU",
                title="SMU",
                level_id=nobrade["fundo"].level_id,
                parent_id=root.description_id,
            )
        )
        hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP IPPUC",
                title="IPPUC",
                level_id=nobrade["fundo"].level_id,
                parent_id=root.description_id,
            )
        )

        tree = hierarchy.tree(root_id=fund.description_id, max_depth=None, limit=10, offset=0)
        assert tree.total == 1
        assert tree.items[0].description_id == fund.description_id

        whole = hierarchy.tree(root_id=root.description_id, max_depth=None, limit=10, offset=0)
        assert whole.total == 3
        assert [item.path for item in whole.items] == sorted(item.path for item in whole.items)


class TestTheGuards:
    def test_a_cycle_is_refused(self, db_session, hierarchy, nobrade):
        root = hierarchy.create_node(
            CreateHierarchyNodeCommand(reference_code="BR PRADAP", title="Acervo", level_id=nobrade["acervo"].level_id)
        )
        fund = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP SMU",
                title="SMU",
                level_id=nobrade["fundo"].level_id,
                parent_id=root.description_id,
            )
        )
        with pytest.raises(InvalidHierarchyMoveError, match="ciclo"):
            hierarchy.move(root.description_id, MoveNodeCommand(new_parent_id=fund.description_id))
        _assert_invariant(db_session)

    def test_a_node_cannot_be_its_own_parent(self, db_session, hierarchy, nobrade):
        node = hierarchy.create_node(
            CreateHierarchyNodeCommand(reference_code="BR PRADAP", title="Acervo", level_id=nobrade["acervo"].level_id)
        )
        with pytest.raises(InvalidHierarchyMoveError, match="si mesma"):
            hierarchy.move(node.description_id, MoveNodeCommand(new_parent_id=node.description_id))

    def test_an_item_may_not_receive_a_child(self, db_session, hierarchy, nobrade):
        parent = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP L1",
                title="Item",
                level_id=nobrade["item"].level_id,
                parent_id=_make_dossier(hierarchy, nobrade),
            )
        )
        with pytest.raises(InvalidHierarchyMoveError, match="não admite filhos"):
            hierarchy.create_node(
                CreateHierarchyNodeCommand(
                    reference_code="BR PRADAP L2",
                    title="Filho",
                    level_id=nobrade["item"].level_id,
                    parent_id=parent.description_id,
                )
            )

    def test_a_dossier_may_not_be_created_at_the_root(self, hierarchy, nobrade):
        with pytest.raises(InvalidHierarchyMoveError, match="raiz"):
            hierarchy.create_node(
                CreateHierarchyNodeCommand(
                    reference_code="BR PRADAP D1", title="Dossiê", level_id=nobrade["dossie"].level_id
                )
            )

    def test_an_item_may_not_be_promoted_to_the_root(self, db_session, hierarchy, nobrade):
        dossier = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP D2",
                title="Dossiê",
                level_id=nobrade["dossie"].level_id,
                parent_id=_make_fund(hierarchy, nobrade),
            )
        )
        item = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP D2 I1",
                title="Item",
                level_id=nobrade["item"].level_id,
                parent_id=dossier.description_id,
            )
        )
        with pytest.raises(InvalidHierarchyMoveError, match="raiz"):
            hierarchy.move(item.description_id, MoveNodeCommand(new_parent_id=None))


def _make_fund(hierarchy, nobrade):
    root = hierarchy.create_node(
        CreateHierarchyNodeCommand(reference_code="BR PRADAP", title="Acervo", level_id=nobrade["acervo"].level_id)
    )
    fund = hierarchy.create_node(
        CreateHierarchyNodeCommand(
            reference_code="BR PRADAP SMU",
            title="SMU",
            level_id=nobrade["fundo"].level_id,
            parent_id=root.description_id,
        )
    )
    return fund.description_id


def _make_dossier(hierarchy, nobrade):
    fund_id = _make_fund(hierarchy, nobrade)
    dossier = hierarchy.create_node(
        CreateHierarchyNodeCommand(
            reference_code="BR PRADAP SMU D1",
            title="Dossiê",
            level_id=nobrade["dossie"].level_id,
            parent_id=fund_id,
        )
    )
    return dossier.description_id


class TestTheMoveLeavesATrail:
    def test_the_before_and_after_are_recorded_in_the_review_history(self, db_session, hierarchy, generate_archive_doc):
        """
        Moving is a curation decision, so it belongs in the same history as every other human edit.

        It does **not** lock the description as ``HUMAN_APPROVED``: hierarchy is arrangement, not
        content, and no AI worker writes these columns — while locking would freeze the enrichment
        of a fund for a decision about where it sits.
        """
        target = generate_archive_doc(description_id="target-1")
        moving = generate_archive_doc(description_id="moving-1")

        hierarchy.move(moving.description_id, MoveNodeCommand(new_parent_id=target.description_id, changed_by="ana"))

        revisions = db_session.scalars(
            select(ArchiveDocumentRevision).where(ArchiveDocumentRevision.description_id == moving.description_id)
        ).all()
        assert len(revisions) == 1
        assert revisions[0].changed_by == "ana"
        assert set(revisions[0].changes) == {"parent_id", "path"}

        moved = db_session.get(ArchiveDocument, moving.description_id)
        assert moved is not None
        assert moved.review_status.value == "PENDING_AI"
        _assert_invariant(db_session)


class TestDiagnostics:
    def test_an_orphan_is_reported_while_its_level_demands_a_parent(self, db_session, hierarchy, nobrade):
        """Every one of the 3,608 real descriptions starts here: the tree must be materialised."""
        db_session.add(
            ArchiveDocument(
                description_id="orphan-1",
                original_title="Dossiê órfão",
                staging_content_hash="h",
                level_id=nobrade["dossie"].level_id,
            )
        )
        db_session.flush()

        page = hierarchy.diagnostics(str(HierarchyIssue.ORPHAN), limit=10, offset=0)
        assert page.total == 1
        assert page.items[0].description_id == "orphan-1"

    def test_the_dossier_case_is_the_narrower_report(self, db_session, hierarchy, nobrade):
        db_session.add(
            ArchiveDocument(
                description_id="orphan-2",
                original_title="Dossiê órfão",
                staging_content_hash="h",
                level_id=nobrade["dossie"].level_id,
            )
        )
        db_session.add(ArchiveDocument(description_id="free-1", original_title="Fundo", staging_content_hash="h"))
        db_session.flush()

        page = hierarchy.diagnostics(str(HierarchyIssue.DOSSIER_WITHOUT_PARENT), limit=10, offset=0)
        assert [item.description_id for item in page.items] == ["orphan-2"]

    def test_a_broken_path_is_found(self, db_session, hierarchy, nobrade):
        """The invariant is queried, not trusted: 'should always be empty' is a claim to falsify."""
        root = hierarchy.create_node(
            CreateHierarchyNodeCommand(reference_code="BR PRADAP", title="Acervo", level_id=nobrade["acervo"].level_id)
        )
        child = hierarchy.create_node(
            CreateHierarchyNodeCommand(
                reference_code="BR PRADAP SMU",
                title="SMU",
                level_id=nobrade["fundo"].level_id,
                parent_id=root.description_id,
            )
        )
        # Simulates a writer that bypassed the service.
        db_session.execute(
            text("UPDATE archive_documents SET path = 'inventado' WHERE description_id = :id"),
            {"id": child.description_id},
        )
        db_session.expire_all()

        page = hierarchy.diagnostics(str(HierarchyIssue.PATH_DIVERGENCE), limit=10, offset=0)
        assert [item.description_id for item in page.items] == [child.description_id]

    def test_an_unclassified_description_is_reported(self, db_session, hierarchy):
        db_session.add(
            ArchiveDocument(description_id="nolevel-1", original_title="Sem nível", staging_content_hash="h")
        )
        db_session.flush()
        page = hierarchy.diagnostics(str(HierarchyIssue.UNKNOWN_LEVEL), limit=10, offset=0)
        assert [item.description_id for item in page.items] == ["nolevel-1"]

    def test_the_depth_mismatch_learns_its_norm_from_the_collection(self, db_session, hierarchy, nobrade):
        """
        Ten Items among twelve Dossiês at the same code depth: the minority is what gets flagged.

        A depth with a tie flags nothing, which is why the two Seções and two Séries at four tokens
        stay silent — there is no norm there to violate.
        """
        for index in range(12):
            db_session.add(
                ArchiveDocument(
                    description_id=f"deep-{index}",
                    original_title=f"Processo {index}",
                    staging_content_hash="h",
                    reference_code=f"BR PRADAP SMU ED AL CONSTR {1000 + index} 19{index:02d}",
                    level_id=nobrade["dossie" if index < 10 else "item"].level_id,
                    review_status="PENDING_AI",
                )
            )
        db_session.flush()

        page = hierarchy.diagnostics(str(HierarchyIssue.LEVEL_DEPTH_MISMATCH), limit=50, offset=0)
        assert page.total == 2
        assert {item.description_id for item in page.items} == {"deep-10", "deep-11"}
        assert page.items[0].detail["expected_ordinal"] == 4
        # The level name travels with the row: these diagnostics classify a detached projection, so
        # it cannot be read through the relationship.
        assert {item.level for item in page.items} == {"Item Documental"}

    def test_an_unknown_issue_is_refused(self, hierarchy):
        with pytest.raises(InvalidHierarchyMoveError):
            hierarchy.diagnostics("NAO_EXISTE", limit=1, offset=0)


class TestMissingNodes:
    def test_a_missing_node_is_a_not_found(self, hierarchy):
        with pytest.raises(HierarchyNodeNotFoundError):
            hierarchy.children("nao-existe")

    def test_a_tree_rooted_at_a_missing_node_is_a_not_found(self, hierarchy):
        with pytest.raises(HierarchyNodeNotFoundError):
            hierarchy.tree(root_id="nao-existe", max_depth=None, limit=10, offset=0)
