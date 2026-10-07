"""
The proposal: what the reference codes imply, and that nothing is written.

The fixture reproduces the shape of the real collection in miniature — the two families that
behave differently, the pure-arrangement record that holds nothing, and the plural/singular
collision. The read-only assertion is the one the phase promises: the archivist reviews a
proposal, and the proposal has no side effect to review.
"""

from sqlalchemy import func, select, text

from scrinalia.domains.archive.domain.hierarchy import HierarchyIssue, ProposalFlag
from scrinalia.domains.archive.models import ArchiveDocument
from scrinalia.domains.archive.repository.hierarchy_repo import HierarchyRepository
from scrinalia.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from scrinalia.domains.archive.schemas.hierarchy_schema import HierarchyProposalCommand
from scrinalia.domains.archive.services.hierarchy_proposal_service import HierarchyProposalService


def _service(db_session) -> HierarchyProposalService:
    return HierarchyProposalService(HierarchyRepository(db_session), LevelCatalogRepository(db_session))


def _seed_collection(db_session, nobrade, generate_archive_doc) -> None:
    """
    The shape of the acervo, in miniature.

    * ``FOTOGRAFIA <serial>`` — 2,391 items in the real collection, all sharing one rung;
    * ``SMU ED AL CONSTR <process> <year>`` — 1,123 dossiês, the family the naive slice broke;
    * ``FOTOGRAFIAS`` — the existing Série record, holding nothing, one letter from the rung above;
    * ``SGM OUVIDORIA`` — a declared Seção that no document hangs from.
    """
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
    generate_archive_doc(
        description_id="secao-ouvidoria",
        reference_code="BR PRADAP SGM OUVIDORIA",
        level_id=nobrade["secao"].level_id,
    )


def _by_code(response) -> dict:
    return {node.code: node for node in response.nodes}


class TestTheProposedTree:
    def test_the_codes_collapse_to_the_rungs_a_human_can_review(
        self, db_session, seed_nobrade_levels, generate_archive_doc
    ):
        """
        Seven documents, and the rungs they imply — not seven nodes per document.

        This is the whole point of the vocabulary-aware slicer: the 1,123-document SMU family
        becomes one chain of containers instead of 1,123 parents of one document.
        """
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        response = _service(db_session).propose(HierarchyProposalCommand())
        codes = _by_code(response)

        assert codes["BR PRADAP"].document_count == 7
        assert codes["BR PRADAP SMU ED AL CONSTR"].document_count == 2
        assert codes["BR PRADAP IPPUC FOTOGRAFIA"].document_count == 3
        # The naive slice would have produced one rung per document here.
        assert "BR PRADAP SMU ED AL CONSTR 1000 1920" not in codes

    def test_a_record_that_holds_nothing_is_still_a_rung(self, db_session, seed_nobrade_levels, generate_archive_doc):
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        node = _by_code(_service(db_session).propose(HierarchyProposalCommand()))["BR PRADAP IPPUC FOTOGRAFIAS"]

        assert node.status == "EXISTS"
        assert node.existing_description_id == "serie-fotografias"
        assert node.document_count == 0
        assert str(ProposalFlag.RECORD_WITHOUT_DOCUMENTS) in node.flags

    def test_the_plural_collision_is_flagged_and_left_for_the_archivist(
        self, db_session, seed_nobrade_levels, generate_archive_doc
    ):
        """
        ``FOTOGRAFIA`` (the rung of 2,391 items) versus ``FOTOGRAFIAS`` (the existing Série).

        The proposal does **not** join them and does **not** create the singular silently: the pair
        is flagged and the node is marked ambiguous, because only the archivist knows whether the
        items hang from the Série or need a node of their own.
        """
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        response = _service(db_session).propose(HierarchyProposalCommand())
        codes = _by_code(response)
        singular = codes["BR PRADAP IPPUC FOTOGRAFIA"]
        plural = codes["BR PRADAP IPPUC FOTOGRAFIAS"]

        assert str(HierarchyIssue.NEAR_DUPLICATE_NODE) in singular.flags
        assert str(HierarchyIssue.NEAR_DUPLICATE_NODE) in plural.flags
        assert singular.status == "AMBIGUOUS"
        assert response.ambiguous_nodes == 1

    def test_an_anchored_rung_takes_the_level_of_its_record(
        self, db_session, seed_nobrade_levels, generate_archive_doc
    ):
        """An existing record *is* the archivist's statement, so it is the only anchor."""
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        node = _by_code(_service(db_session).propose(HierarchyProposalCommand()))["BR PRADAP IPPUC FOTOGRAFIAS"]

        assert node.ordinal_inferred is False
        assert node.proposed_level_code == "serie"

    def test_an_inferred_rung_says_so(self, db_session, seed_nobrade_levels, generate_archive_doc):
        """
        The depth of a code does **not** decide the level in this collection: five tokens hold
        Items, a Série and a Seção at once. So a rung with no declared record is a proposal.
        """
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        codes = _by_code(_service(db_session).propose(HierarchyProposalCommand()))

        assert codes["BR PRADAP"].ordinal_inferred is True
        assert codes["BR PRADAP"].proposed_level_code == "acervo"
        assert codes["BR PRADAP SMU"].proposed_level_code == "fundo"
        # A container sits one rung above what it holds: the items are Items, so it proposes Dossiê.
        assert codes["BR PRADAP IPPUC FOTOGRAFIA"].proposed_level_code == "dossie"

    def test_the_suggested_name_comes_from_the_measured_vocabulary(
        self, db_session, seed_nobrade_levels, generate_archive_doc
    ):
        """A suggestion, never an application: renaming would be a write."""
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        codes = _by_code(_service(db_session).propose(HierarchyProposalCommand()))

        assert codes["BR PRADAP SMU"].suggested_name.startswith("SMU - Secretaria Municipal de Urbanismo")
        assert codes["BR PRADAP IPPUC FOTOGRAFIA"].suggested_name == "Registros Fotográficos"
        # An unknown token is left without a suggestion instead of being invented.
        assert codes["BR PRADAP"].suggested_name == "Acervo da entidade custodiadora"


class TestTheReport:
    def test_the_counts_describe_the_whole_proposal_even_when_the_page_is_capped(
        self, db_session, seed_nobrade_levels, generate_archive_doc
    ):
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        capped = _service(db_session).propose(HierarchyProposalCommand(limit=2))

        assert capped.total_codes == 7
        assert capped.total_nodes > 2
        assert len(capped.nodes) == 2
        assert capped.existing_nodes == 2

    def test_existing_rungs_can_be_left_out_of_the_page(self, db_session, seed_nobrade_levels, generate_archive_doc):
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        response = _service(db_session).propose(HierarchyProposalCommand(include_existing=False))
        assert all(node.status != "EXISTS" for node in response.nodes)
        assert response.existing_nodes == 2

    def test_the_codes_the_slicer_cannot_read_cleanly_are_listed(
        self, db_session, seed_nobrade_levels, generate_archive_doc
    ):
        """~20 of the 3,608 real codes carry a malformed tail; they are surfaced, not swallowed."""
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        generate_archive_doc(
            description_id="malformed-1",
            reference_code="BR PRADAP SMU ED AL CONSTR 10047 (1)",
            level_id=nobrade["dossie"].level_id,
        )
        generate_archive_doc(
            description_id="malformed-2",
            reference_code="BR PRADAP SEPLAD OF 478 1959 DUP",
            level_id=nobrade["dossie"].level_id,
        )

        response = _service(db_session).propose(HierarchyProposalCommand())

        assert "BR PRADAP SMU ED AL CONSTR 10047 (1)" in response.unparsed_codes
        assert "BR PRADAP SEPLAD OF 478 1959 DUP" in response.unparsed_codes

    def test_the_flag_histogram_is_available_without_walking_the_nodes(
        self, db_session, seed_nobrade_levels, generate_archive_doc
    ):
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        response = _service(db_session).propose(HierarchyProposalCommand())

        assert response.flags[str(ProposalFlag.ORDINAL_INFERRED)] > 0
        assert response.flags[str(HierarchyIssue.NEAR_DUPLICATE_NODE)] == 2


class TestTheProposalDoesNotWrite:
    def test_the_database_is_untouched_by_a_proposal_run(self, db_session, seed_nobrade_levels, generate_archive_doc):
        """
        The promise of the phase, asserted the same way the macro-category dry run was: run the
        routine and prove the collection did not move.
        """
        nobrade = {level.code: level for level in seed_nobrade_levels()}
        _seed_collection(db_session, nobrade, generate_archive_doc)

        def snapshot() -> list[tuple]:
            return db_session.execute(
                select(
                    ArchiveDocument.description_id,
                    ArchiveDocument.parent_id,
                    ArchiveDocument.path,
                    ArchiveDocument.level_id,
                    ArchiveDocument.reference_code,
                ).order_by(ArchiveDocument.description_id)
            ).all()

        before = snapshot()
        before_documents = db_session.scalar(select(func.count()).select_from(ArchiveDocument))

        _service(db_session).propose(HierarchyProposalCommand())

        assert snapshot() == before
        assert db_session.scalar(select(func.count()).select_from(ArchiveDocument)) == before_documents
        # And no node was created: the only rows are the ones the fixture inserted.
        created = db_session.scalar(
            text("SELECT count(*) FROM archive_documents WHERE staging_content_hash = 'curation:created-node'")
        )
        assert created == 0
