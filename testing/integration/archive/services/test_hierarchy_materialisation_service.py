"""
Materialising the arrangement, driven by a recorded decision, against the real database.

The fixture reproduces the two shapes the real collection forced into the design:

* ``BR PRADAP SMU ED AL CONSTR`` — where **two alphabetic segments are one level** of the
  arrangement, something no slicer can know because the evidence is not in the string; and
* ``BR PRADAP IPPUC FOTOGRAFIA`` versus the existing Série ``BR PRADAP IPPUC FOTOGRAFIAS`` — where
  the documents of one rung really belong under a record spelled one letter differently.

Both are resolved by a person through ``collapse_into_code``, and both are asserted here because
they are the whole reason the plan catalogue exists.
"""

import pytest
from sqlalchemy import func, select, text

from scrinalia.core.author import Author
from scrinalia.domains.archive.domain.hierarchy import PlanStatus, plan_flag_vocabulary
from scrinalia.domains.archive.exceptions import (
    DescriptionLevelNotFoundError,
    HierarchyPlanNotFoundError,
    InvalidHierarchyPlanError,
    MaterialisationAlreadyUndoneError,
    MaterialisationNotFoundError,
)
from scrinalia.domains.archive.models import ArchiveDocument
from scrinalia.domains.archive.repository.collection_vocabulary_repo import CollectionVocabularyRepository
from scrinalia.domains.archive.repository.hierarchy_repo import HierarchyRepository
from scrinalia.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from scrinalia.domains.archive.schemas.hierarchy_schema import (
    HierarchyMaterialisationRequest,
    HierarchyPlanDecisionCommand,
)
from scrinalia.domains.archive.services.hierarchy_materialisation_service import (
    HierarchyMaterialisationService,
)
from scrinalia.domains.archive.services.hierarchy_proposal_service import HierarchyProposalService


@pytest.fixture
def nobrade(seed_nobrade_levels):
    return {level.code: level for level in seed_nobrade_levels()}


@pytest.fixture
def service(db_session, reference_vocabulary):
    # The suggestion needs the collection vocabulary, and the test schema is built by
    # ``create_all``: without seeding the catalogue the proposal would suggest no name at all.
    reference_vocabulary()
    repo = HierarchyRepository(db_session)
    catalog = LevelCatalogRepository(db_session)
    return HierarchyMaterialisationService(
        repo,
        catalog,
        HierarchyProposalService(repo, catalog, CollectionVocabularyRepository(db_session)),
    )


@pytest.fixture
def collection(db_session, nobrade, generate_archive_doc):
    """The miniature collection: the SMU family, the plural collision and a record-only rung."""
    for serial in range(3):
        generate_archive_doc(
            description_id=f"foto-{serial}",
            reference_code=f"BR PRADAP IPPUC FOTOGRAFIA {serial:05d}",
            level_id=nobrade["item"].level_id,
        )
    for index in range(2):
        generate_archive_doc(
            description_id=f"smu-{index}",
            reference_code=f"BR PRADAP SMU ED AL CONSTR {1000 + index} 19{20 + index}",
            level_id=nobrade["dossie"].level_id,
        )
    generate_archive_doc(
        description_id="serie-fotografias",
        reference_code="BR PRADAP IPPUC FOTOGRAFIAS",
        level_id=nobrade["serie"].level_id,
    )
    return db_session


def _approve(service, nobrade, decisions: dict[str, tuple[str, str, str | None]], status_by_default: str = "REJECTED"):
    """Approves the rungs named in ``decisions`` and applies the default verdict to the rest."""
    for plan in service.list_plans(status=None, limit=200, offset=0).items:
        if plan.code in decisions:
            level_code, title, collapse = decisions[plan.code]
            service.decide(
                plan.plan_id,
                HierarchyPlanDecisionCommand(
                    status="APPROVED",
                    level_id=nobrade[level_code].level_id,
                    title=title,
                    collapse_into_code=collapse,
                    decided_by=Author(name="ana"),
                ),
            )
        else:
            service.decide(
                plan.plan_id, HierarchyPlanDecisionCommand(status=status_by_default, decided_by=Author(name="ana"))
            )


def _full_decisions() -> dict[str, tuple[str, str, str | None]]:
    return {
        "BR PRADAP": ("acervo", "Acervo da entidade custodiadora", None),
        "BR PRADAP IPPUC": ("fundo", "IPPUC", None),
        # The rung the items imply collapses into the Série record that already exists.
        "BR PRADAP IPPUC FOTOGRAFIA": ("serie", "Registros Fotográficos", "BR PRADAP IPPUC FOTOGRAFIAS"),
        "BR PRADAP IPPUC FOTOGRAFIAS": ("serie", "Registros Fotográficos", None),
        "BR PRADAP SMU": ("fundo", "SMU", None),
        "BR PRADAP SMU ED": ("secao", "Edificações", None),
        # The archivist's correction: AL and CONSTR are ONE level.
        "BR PRADAP SMU ED AL": ("serie", "Alvenaria - Construções", None),
        "BR PRADAP SMU ED AL CONSTR": ("serie", "Alvenaria - Construções", "BR PRADAP SMU ED AL"),
        "BR PRADAP SGM OUVIDORIA": ("secao", "Ouvidoria Municipal de Curitiba", None),
    }


def _assert_invariant(db_session) -> None:
    broken = db_session.execute(
        text(
            """
            SELECT d.description_id
              FROM archive_documents d
              LEFT JOIN archive_documents p ON p.description_id = d.parent_id
             WHERE d.path <> coalesce(p.path || '.', '') || d.description_id
            """
        )
    ).all()
    assert broken == []


class TestTheCatalogueOfDecisions:
    def test_the_suggestion_registers_every_proposed_rung(self, service, collection):
        result = service.suggest()
        assert result.created == result.total
        assert result.total > 0

    def test_every_flag_a_row_carries_is_in_the_published_vocabulary(self, service, collection):
        """
        The rows are the source of truth for what the vocabulary must contain.

        A plan row is assembled from four vocabularies (the proposal's, the near-duplicate issue,
        the ladder violation and the slicer's), and a front that groups by ``flags`` can only
        translate the codes the API publishes. This asserts the published union against the flags
        the fixture's rows really carry — the defect that started it was a row carrying
        ``NEAR_DUPLICATE_NODE`` while the endpoint advertised three other codes.
        """
        service.suggest()
        published = set(plan_flag_vocabulary())
        carried = {flag for plan in service.list_plans(None, 200, 0).items for flag in (plan.flags or [])}

        assert carried, "the fixture collection must produce at least one flag"
        assert carried <= published

    def test_the_list_reports_the_verdict_of_the_whole_catalogue(self, service, collection, nobrade):
        """
        The progress bar counts every rung, not the page.

        A filtered page carries the counts of the catalogue anyway, because "34 de 52 decididos" is
        a statement about all 52 — deriving it from a page of 20 would make the number depend on the
        filter the archivist happens to have applied.
        """
        service.suggest()
        total = service.list_plans(None, 200, 0).status_counts

        # Every status is present even at zero, so the denominator cannot move as decisions arrive.
        assert set(total) == {str(status) for status in PlanStatus}
        assert total[str(PlanStatus.SUGGESTED)] > 0
        assert total[str(PlanStatus.APPROVED)] == 0

        plan = next(p for p in service.list_plans(None, 200, 0).items if p.code == "BR PRADAP SMU")
        service.decide(plan.plan_id, HierarchyPlanDecisionCommand(status="APPROVED", decided_by=Author(name="ana")))

        after = service.list_plans(status="APPROVED", limit=1, offset=0).status_counts
        assert after[str(PlanStatus.APPROVED)] == 1
        assert after[str(PlanStatus.SUGGESTED)] == total[str(PlanStatus.SUGGESTED)] - 1
        assert sum(after.values()) == sum(total.values())

    def test_a_decision_survives_a_new_suggestion_run(self, service, collection, nobrade):
        """
        The whole reason the catalogue exists: the same ~52 questions must not be asked again, and
        a re-run must not quietly rewrite the numbers the decision was taken on.
        """
        service.suggest()
        plan = next(p for p in service.list_plans(None, 200, 0).items if p.code == "BR PRADAP SMU")
        service.decide(
            plan.plan_id,
            HierarchyPlanDecisionCommand(
                status="APPROVED", level_id=nobrade["fundo"].level_id, title="Meu título", decided_by=Author(name="ana")
            ),
        )

        second = service.suggest()
        again = next(p for p in service.list_plans(None, 200, 0).items if p.code == "BR PRADAP SMU")

        assert second.preserved > 0
        assert again.status == "APPROVED"
        assert again.title == "Meu título"
        assert again.level_id == nobrade["fundo"].level_id

    def test_approving_accepts_the_proposed_level_when_the_archivist_does_not_change_it(self, service, collection):
        """ "Accept as proposed" is a decision too: sending no level keeps the one on the row."""
        service.suggest()
        plan = next(p for p in service.list_plans(None, 200, 0).items if p.code == "BR PRADAP SMU")
        assert plan.level_id is not None  # the proposal already carries the inferred rung

        decided = service.decide(
            plan.plan_id, HierarchyPlanDecisionCommand(status="APPROVED", decided_by=Author(name="ana"))
        )

        assert decided.status == "APPROVED"
        assert decided.level_id == plan.level_id

    def test_a_rung_with_no_level_cannot_be_approved(self, service, collection, db_session):
        """Choosing the rung is the decision the code cannot take; approving without one is not one."""
        service.suggest()
        plan = service.list_plans(None, 200, 0).items[0]
        stored = service.repo.get_plan(plan.plan_id)
        assert stored is not None
        stored.level_id = None
        db_session.flush()

        with pytest.raises(InvalidHierarchyPlanError, match="nível de descrição"):
            service.decide(plan.plan_id, HierarchyPlanDecisionCommand(status="APPROVED", decided_by=Author(name="ana")))

    def test_an_unknown_plan_is_a_not_found(self, service):
        with pytest.raises(HierarchyPlanNotFoundError):
            service.decide(99999, HierarchyPlanDecisionCommand(status="APPROVED"))

    def test_an_unknown_level_is_refused(self, service, collection):
        service.suggest()
        plan = service.list_plans(None, 200, 0).items[0]
        with pytest.raises(DescriptionLevelNotFoundError):
            service.decide(
                plan.plan_id,
                HierarchyPlanDecisionCommand(status="APPROVED", level_id=99999, decided_by=Author(name="ana")),
            )

    def test_collapsing_onto_an_unknown_code_is_refused(self, service, collection, nobrade):
        service.suggest()
        plan = service.list_plans(None, 200, 0).items[0]
        with pytest.raises(InvalidHierarchyPlanError, match="não existe no catálogo"):
            service.decide(
                plan.plan_id,
                HierarchyPlanDecisionCommand(
                    status="APPROVED", level_id=nobrade["serie"].level_id, collapse_into_code="BR INVENTADO"
                ),
            )

    def test_collapsing_a_rung_onto_itself_is_refused(self, service, collection, nobrade):
        service.suggest()
        plan = service.list_plans(None, 200, 0).items[0]
        with pytest.raises(InvalidHierarchyPlanError, match="nele mesmo"):
            service.decide(
                plan.plan_id,
                HierarchyPlanDecisionCommand(
                    status="APPROVED", level_id=nobrade["serie"].level_id, collapse_into_code=plan.code
                ),
            )

    def test_a_collapse_cycle_is_refused(self, service, collection, nobrade):
        service.suggest()
        first, second = service.list_plans(None, 200, 0).items[:2]
        level_id = nobrade["serie"].level_id
        service.decide(
            first.plan_id,
            HierarchyPlanDecisionCommand(status="APPROVED", level_id=level_id, collapse_into_code=second.code),
        )
        with pytest.raises(InvalidHierarchyPlanError, match="ciclo"):
            service.decide(
                second.plan_id,
                HierarchyPlanDecisionCommand(status="APPROVED", level_id=level_id, collapse_into_code=first.code),
            )


class TestPreview:
    def test_the_dry_run_reports_what_the_write_would_do(self, service, collection, nobrade):
        service.suggest()
        _approve(service, nobrade, _full_decisions())

        preview = service.preview(HierarchyMaterialisationRequest())

        assert preview.nodes_to_create == 5  # Acervo, IPPUC, SMU, SMU ED, SMU ED AL
        assert preview.nodes_to_adopt == 1  # the existing Série record
        assert preview.documents_to_attach == 5  # 3 photos + 2 processes
        assert preview.remaining_orphans == 0

    def test_the_dry_run_writes_nothing(self, service, collection, nobrade, db_session):
        service.suggest()
        _approve(service, nobrade, _full_decisions())

        before = db_session.execute(
            select(ArchiveDocument.description_id, ArchiveDocument.parent_id, ArchiveDocument.path).order_by(
                ArchiveDocument.description_id
            )
        ).all()
        service.preview(HierarchyMaterialisationRequest())
        after = db_session.execute(
            select(ArchiveDocument.description_id, ArchiveDocument.parent_id, ArchiveDocument.path).order_by(
                ArchiveDocument.description_id
            )
        ).all()

        assert before == after
        assert db_session.scalar(select(func.count()).select_from(ArchiveDocument)) == 6

    def test_a_rejected_rung_leaves_its_descriptions_counted_as_orphans(self, service, collection, nobrade):
        """The escape hatch for a code that lies: reject it and the descriptions attach higher."""
        service.suggest()
        decisions = _full_decisions()
        del decisions["BR PRADAP SMU ED AL"]
        del decisions["BR PRADAP SMU ED AL CONSTR"]
        _approve(service, nobrade, decisions)

        preview = service.preview(HierarchyMaterialisationRequest())

        # The two SMU processes still reach SMU ED, so they are not orphans at all.
        assert preview.remaining_orphans == 0

    def test_applying_nothing_approved_is_refused(self, service, collection):
        service.suggest()
        with pytest.raises(InvalidHierarchyPlanError, match="Nenhum nó aprovado"):
            service.apply(HierarchyMaterialisationRequest())


class TestApply:
    def _materialise(self, service, collection, nobrade):
        service.suggest()
        _approve(service, nobrade, _full_decisions())
        return service.apply(HierarchyMaterialisationRequest(changed_by=Author(name="ana")))

    def test_the_tree_is_materialised_and_the_invariant_holds(self, service, collection, nobrade, db_session):
        result = self._materialise(service, collection, nobrade)

        assert result.created_nodes == 5
        assert result.adopted_nodes == 1
        assert result.documents_attached == 5
        _assert_invariant(db_session)

    def test_two_alphabetic_segments_become_one_level(self, service, collection, nobrade, db_session):
        """
        The archivist's correction, asserted on the tree it produces.

        ``AL`` must exist and ``AL CONSTR`` must not: the two code segments are one rung, and only a
        person could say so.
        """
        self._materialise(service, collection, nobrade)

        nodes = db_session.scalars(
            select(ArchiveDocument).where(ArchiveDocument.reference_code.like("%SMU ED AL%"))
        ).all()
        created = {node.reference_code for node in nodes if node.staging_content_hash == "curation:created-node"}

        assert created == {"BR PRADAP SMU ED AL"}

        al_node = next(node for node in nodes if node.reference_code == "BR PRADAP SMU ED AL")
        assert al_node.parent_id is not None
        # Both processes hang under the single level, not under a second one.
        processes = db_session.scalars(
            select(ArchiveDocument).where(ArchiveDocument.description_id.in_(["smu-0", "smu-1"]))
        ).all()
        assert {process.parent_id for process in processes} == {al_node.description_id}

    def test_a_rung_can_be_collapsed_onto_an_existing_record(self, service, collection, nobrade, db_session):
        """``FOTOGRAFIA`` and the Série ``FOTOGRAFIAS`` are one rung, one letter apart."""
        self._materialise(service, collection, nobrade)

        existing = db_session.get(ArchiveDocument, "serie-fotografias")
        photos = db_session.scalars(
            select(ArchiveDocument).where(ArchiveDocument.description_id.in_(["foto-0", "foto-1", "foto-2"]))
        ).all()

        assert existing is not None
        assert {photo.parent_id for photo in photos} == {"serie-fotografias"}
        # No mirror node was created for the singular spelling.
        mirrors = db_session.scalars(
            select(ArchiveDocument).where(
                ArchiveDocument.reference_code == "BR PRADAP IPPUC FOTOGRAFIA",
                ArchiveDocument.staging_content_hash == "curation:created-node",
            )
        ).all()
        assert mirrors == []

    def test_the_existing_record_is_adopted_and_keeps_its_identity(self, service, collection, nobrade, db_session):
        self._materialise(service, collection, nobrade)
        adopted = db_session.get(ArchiveDocument, "serie-fotografias")
        assert adopted is not None
        assert adopted.staging_content_hash != "curation:created-node"
        assert adopted.parent_id is not None  # now under the IPPUC fund

    def test_the_run_is_idempotent(self, service, collection, nobrade):
        """A second apply finds everything already placed: nothing is created, nothing is moved."""
        self._materialise(service, collection, nobrade)

        second = service.apply(HierarchyMaterialisationRequest(changed_by=Author(name="ana")))

        assert second.created_nodes == 0
        assert second.documents_attached == 0

    def test_the_preview_and_the_apply_agree(self, service, collection, nobrade, db_session):
        """
        A dry run that lies is worse than no dry run: the numbers the archivist reads have to be
        the numbers the write produces.
        """
        service.suggest()
        _approve(service, nobrade, _full_decisions())
        preview = service.preview(HierarchyMaterialisationRequest())

        result = service.apply(HierarchyMaterialisationRequest(changed_by=Author(name="ana")))

        assert preview.nodes_to_create == result.created_nodes
        assert preview.nodes_to_adopt == result.adopted_nodes
        assert preview.documents_to_attach == result.documents_attached


class TestUndo:
    def _materialise(self, service, collection, nobrade):
        service.suggest()
        _approve(service, nobrade, _full_decisions())
        return service.apply(HierarchyMaterialisationRequest(changed_by=Author(name="ana")))

    def test_the_collection_goes_back_exactly_where_it_was(self, service, collection, nobrade, db_session):
        before = db_session.execute(
            select(ArchiveDocument.description_id, ArchiveDocument.parent_id, ArchiveDocument.path).order_by(
                ArchiveDocument.description_id
            )
        ).all()

        result = self._materialise(service, collection, nobrade)
        service.undo(result.materialisation_id, undone_by=Author(name="ana"))

        after = db_session.execute(
            select(ArchiveDocument.description_id, ArchiveDocument.parent_id, ArchiveDocument.path).order_by(
                ArchiveDocument.description_id
            )
        ).all()
        assert after == before
        _assert_invariant(db_session)

    def test_the_created_rungs_are_removed(self, service, collection, nobrade, db_session):
        result = self._materialise(service, collection, nobrade)
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(ArchiveDocument)
                .where(ArchiveDocument.staging_content_hash == "curation:created-node")
            )
            == result.created_nodes
        )

        service.undo(result.materialisation_id, undone_by=Author(name="ana"))

        assert (
            db_session.scalar(
                select(func.count())
                .select_from(ArchiveDocument)
                .where(ArchiveDocument.staging_content_hash == "curation:created-node")
            )
            == 0
        )

    def test_undoing_twice_is_a_conflict(self, service, collection, nobrade):
        result = self._materialise(service, collection, nobrade)
        service.undo(result.materialisation_id, undone_by=Author(name="ana"))
        with pytest.raises(MaterialisationAlreadyUndoneError):
            service.undo(result.materialisation_id, undone_by=Author(name="ana"))

    def test_an_unknown_run_is_a_not_found(self, service):
        with pytest.raises(MaterialisationNotFoundError):
            service.undo(99999, undone_by=Author(name="ana"))

    def test_the_ledger_entry_survives_the_reversal(self, service, collection, nobrade):
        result = self._materialise(service, collection, nobrade)
        service.undo(result.materialisation_id, undone_by=Author(name="ana"))

        log = service.list_log(include_undone=True, limit=10, offset=0)
        assert log.total == 1
        assert log.items[0].undone_at is not None
        assert log.items[0].undone_by == "ana"
        assert log.items[0].changed_rows > 0

    def test_the_ledger_searches_the_author_and_the_note(self, service, collection, nobrade):
        """The two fields that let someone find "the run Ana did when the microfilm was attached"."""
        service.suggest()
        _approve(service, nobrade, _full_decisions())
        service.apply(HierarchyMaterialisationRequest(changed_by=Author(name="ana"), note="microfilmes anexados"))

        assert service.list_log(include_undone=True, limit=10, offset=0, term="ana").total == 1
        assert service.list_log(include_undone=True, limit=10, offset=0, term="microfilme").total == 1
        assert service.list_log(include_undone=True, limit=10, offset=0, term="ninguém").total == 0
        # A ``%`` is a character, not "everything": the ledger must not answer the whole trail.
        assert service.list_log(include_undone=True, limit=10, offset=0, term="%").total == 0

    def test_a_run_that_gained_descriptions_later_cannot_be_undone_blindly(
        self, service, collection, nobrade, db_session
    ):
        """
        Reversing would silently detach work that was never part of the decision, so it is refused
        with the reason instead of done quietly.
        """
        result = self._materialise(service, collection, nobrade)
        created = db_session.scalars(
            select(ArchiveDocument).where(ArchiveDocument.staging_content_hash == "curation:created-node")
        ).all()
        intruder = min(created, key=lambda node: node.path.count("."))

        db_session.add(
            ArchiveDocument(
                description_id="late-arrival",
                original_title="Chegou depois",
                staging_content_hash="h",
                parent_id=intruder.description_id,
                path=f"{intruder.path}.late-arrival",
            )
        )
        db_session.flush()

        with pytest.raises(InvalidHierarchyPlanError, match="recebeu descrições depois"):
            service.undo(result.materialisation_id, undone_by=Author(name="ana"))

    def test_the_rungs_that_pointed_at_a_deleted_node_go_back_to_not_materialised(
        self, service, collection, nobrade, db_session
    ):
        """
        A rung that adopted an existing record still points at it after the undo — the record was
        not removed. Only the rungs that pointed at a node this run created are cleared, or the next
        apply would try to attach descriptions to a row that no longer exists.
        """
        result = self._materialise(service, collection, nobrade)
        created_ids = {
            node.description_id
            for node in db_session.scalars(
                select(ArchiveDocument).where(ArchiveDocument.staging_content_hash == "curation:created-node")
            ).all()
        }
        service.undo(result.materialisation_id, undone_by=Author(name="ana"))

        plans = service.list_plans(None, 200, 0).items
        assert created_ids
        assert all(
            plan.materialised_description_id is None
            for plan in plans
            if plan.materialised_description_id in created_ids
        )
        assert all(
            plan.materialised_description_id is None
            for plan in plans
            if plan.status == "APPROVED" and plan.materialised_description_id in created_ids
        )

    def test_applying_again_after_an_undo_rebuilds_the_same_tree(self, service, collection, nobrade, db_session):
        first = self._materialise(service, collection, nobrade)
        service.undo(first.materialisation_id, undone_by=Author(name="ana"))
        second = service.apply(HierarchyMaterialisationRequest(changed_by=Author(name="ana")))

        assert second.created_nodes == first.created_nodes
        assert second.documents_attached == first.documents_attached
        _assert_invariant(db_session)
