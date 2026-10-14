import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import InvalidParam
from scrinalia.domains.archive.repository import EntityRepository
from scrinalia.domains.archive.schemas import ResolveConflictBatchCommand, ResolveConflictCommand
from scrinalia.domains.archive.schemas.entity_schema import (
    ConflictBatchResult,
    ConflictResolutionData,
    ConflictResolutionPlan,
    CrossDomainConflict,
    CrossDomainConflictPage,
    NerPurgeItem,
    NerPurgePlan,
    NerPurgeResult,
)
from scrinalia.domains.archive.services import EntityService
from scrinalia.domains.archive.services.entity_service import MAX_CONFLICT_BATCH_PAIRS

# ==========================================
# TESTS: CROSS DOMAIN
# ==========================================


def test_find_cross_domain_conflicts(mocker: MockerFixture) -> None:
    """Guarantees that the service forwards the correct threshold to the repository and returns the DTOs."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)

    # The port now returns domain DTOs directly (no SQLAlchemy Row leakage).
    conflict = CrossDomainConflict(
        tag_id=1,
        tag_name="Batel",
        entity_id=99,
        entity_name="Batel",
        entity_type="LOC",
        similarity=1.0,
    )
    mock_ent_repo.get_cross_domain_conflicts.return_value = [conflict]

    service = EntityService(
        mock_ent_repo,
    )
    results = service.find_cross_domain_conflicts(threshold=0.90)

    mock_ent_repo.get_cross_domain_conflicts.assert_called_once_with(0.90)
    assert len(results) == 1
    assert results[0].tag_name == "Batel"
    assert results[0].entity_type == "LOC"


def test_resolve_cross_domain_conflict_invalid_winner() -> None:
    """Guarantees the command DTO rejects an invalid winner before it reaches the service."""
    with pytest.raises(ValidationError):
        ResolveConflictCommand(winner="VENCEDOR_FALSO", tag_id=1, entity_id=2)  # type: ignore


def test_resolve_cross_domain_conflict_plans_then_applies(mocker: MockerFixture) -> None:
    """
    The write goes through plan + apply, never straight to the transfer.

    That is what makes every resolution reversible: the apply is the only method that writes the
    ledger row, so a path that skipped the plan would be a path that could forget to record. The
    preview and the write therefore read the same numbers.
    """
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    plan = ConflictResolutionPlan(tag_id=10, tag_name="batel", entity_id=20, entity_name="Batel", entity_type="LOC")
    mock_ent_repo.plan_conflict_resolution.return_value = plan
    mock_ent_repo.apply_conflict_resolution.return_value = ConflictResolutionData(
        winner="ENTITY", documents_transferred=5, resolution_id=7
    )

    service = EntityService(mock_ent_repo)
    command = ResolveConflictCommand(
        winner="ENTITY", tag_id=10, entity_id=20, decided_by=Author(name="ana"), note="bairro"
    )
    result = service.resolve_cross_domain_conflict(command)

    mock_ent_repo.plan_conflict_resolution.assert_called_once_with(10, 20)
    mock_ent_repo.apply_conflict_resolution.assert_called_once_with(
        plan, "ENTITY", source="HUMAN", decided_by=Author(name="ana"), note="bairro"
    )
    assert result.winner == "ENTITY"
    assert result.documents_transferred == 5
    assert result.resolution_id == 7


def test_resolve_cross_domain_conflict_forwards_judge_source(mocker: MockerFixture) -> None:
    """The LLM judge must be recorded as the author of the decision, not the curator."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.plan_conflict_resolution.return_value = ConflictResolutionPlan(
        tag_id=1, tag_name="batel", entity_id=2, entity_name="Batel", entity_type="LOC"
    )
    mock_ent_repo.apply_conflict_resolution.return_value = ConflictResolutionData(winner="TAG", documents_transferred=0)

    service = EntityService(mock_ent_repo)
    service.resolve_cross_domain_conflict(ResolveConflictCommand(winner="TAG", tag_id=1, entity_id=2), source="JUDGE")

    # The judge has no account, and the ledger now says so: ``source`` records that the machine
    # decided, ``decided_by`` stays empty. Before, the second column held the first one's value, so
    # "who decided" answered "JUDGE" and no query could tell a person from the worker.
    assert mock_ent_repo.apply_conflict_resolution.call_args.kwargs["source"] == "JUDGE"
    assert mock_ent_repo.apply_conflict_resolution.call_args.kwargs["decided_by"] is None


def test_the_preview_refuses_a_threshold_out_of_range(mocker: MockerFixture) -> None:
    """The dry run validates its own input instead of scanning with a meaningless threshold."""
    service = EntityService(mocker.Mock(spec=EntityRepository))
    with pytest.raises(InvalidParam):
        service.page_cross_domain_conflicts(threshold=1.5)


def test_the_page_forwards_the_pair_kind_that_makes_the_list_usable(mocker: MockerFixture) -> None:
    """
    ``pair_kind`` is the lever that separates the spelling questions from the structural ones, and
    ``entity_type`` narrows the structural population to the category the batch writes.

    It is not called ``scope``: Litestar reserves that name for the ASGI scope, and a handler
    parameter with it silently receives the raw request instead of the query string.
    """
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.page_cross_domain_conflicts.return_value = CrossDomainConflictPage(total=0, limit=50, offset=0)

    service = EntityService(mock_ent_repo)
    service.page_cross_domain_conflicts(
        threshold=0.9, pair_kind="near_duplicate", entity_type="LOC", limit=10, offset=20
    )

    mock_ent_repo.page_cross_domain_conflicts.assert_called_once_with(
        threshold=0.9, pair_kind="near_duplicate", entity_type="LOC", limit=10, offset=20
    )


def test_the_batch_forwards_its_selection_and_bounds_it(mocker: MockerFixture) -> None:
    """
    The selection is the batch's whole input, and the service is where its bounds are enforced.

    A limit outside the range is refused before any pair is written — a click that writes thousands
    of ledger rows is a click nobody reviewed.
    """
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.resolve_conflict_batch.return_value = ConflictBatchResult(winner="ENTITY")

    service = EntityService(mock_ent_repo)
    service.resolve_conflict_batch(
        ResolveConflictBatchCommand(winner="ENTITY", pair_kind="exact_name", entity_type="LOC", limit=25)
    )

    mock_ent_repo.resolve_conflict_batch.assert_called_once_with(
        winner="ENTITY",
        pair_kind="exact_name",
        entity_type="LOC",
        threshold=0.85,
        limit=25,
        decided_by=None,
        note=None,
    )

    for out_of_range in (0, MAX_CONFLICT_BATCH_PAIRS + 1):
        with pytest.raises(InvalidParam):
            service.resolve_conflict_batch(ResolveConflictBatchCommand(winner="TAG", limit=out_of_range))

    with pytest.raises(InvalidParam):
        service.resolve_conflict_batch(ResolveConflictBatchCommand(winner="TAG", threshold=1.5))


# ==========================================
# TESTS: NER EXCLUSIONS
# ==========================================


def test_exclude_terms_from_ner_only_bans(mocker: MockerFixture) -> None:
    """The ban deletes nothing: the retroactive loss is a separate, previewed, ledgered act (#94)."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.add_ner_exclusions.return_value = 1

    service = EntityService(mock_ent_repo)
    created = service.exclude_terms_from_ner([" IPTU ", "iptu"], reason="assunto, não entidade", tag_id=7)

    assert created == 1
    mock_ent_repo.add_ner_exclusions.assert_called_once_with(
        ["iptu", "iptu"], source="HUMAN", reason="assunto, não entidade", tag_id=7
    )


def test_exclude_terms_from_ner_ignores_blank_input(mocker: MockerFixture) -> None:
    """A blank term must not reach the catalog."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    service = EntityService(mock_ent_repo)

    assert service.exclude_terms_from_ner(["   ", ""]) == 0

    mock_ent_repo.add_ner_exclusions.assert_not_called()


def test_exclude_terms_from_ner_defaults_to_human_source(mocker: MockerFixture) -> None:
    """Without an explicit source the decision is attributed to the curator."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.add_ner_exclusions.return_value = 1

    EntityService(mock_ent_repo).exclude_terms_from_ner(["iptu"])

    assert mock_ent_repo.add_ner_exclusions.call_args.kwargs["source"] == "HUMAN"


def test_list_and_remove_ner_exclusions(mocker: MockerFixture) -> None:
    """The catalog is listable and an exclusion can be undone."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.list_ner_exclusions.return_value = []
    mock_ent_repo.remove_ner_exclusions.return_value = 1

    service = EntityService(mock_ent_repo)

    assert list(service.list_ner_exclusions()) == []
    assert service.remove_ner_exclusions(["IPTU"]) == 1

    mock_ent_repo.remove_ner_exclusions.assert_called_once_with(["iptu"])


def test_preview_ner_purge_reads_the_plan_the_write_consumes(mocker: MockerFixture) -> None:
    """The preview is the plan: same ids, same weights, and it promises the ledger's undo."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.plan_ner_purge.return_value = NerPurgePlan(
        excluded_terms=["iptu"],
        items=[
            NerPurgeItem(
                entity_id=11,
                name="iptu",
                entity_type="ORG",
                excluded_term="iptu",
                document_ids=["d1", "d2"],
                synonym_names=["iptu do batel"],
            )
        ],
    )

    preview = EntityService(mock_ent_repo).preview_ner_purge()

    assert preview.excluded_terms == ["iptu"]
    assert preview.total_entities == 1
    assert preview.total_documents == 2
    assert preview.reversible is True
    assert preview.entities[0].entity_id == 11
    assert preview.entities[0].document_count == 2
    mock_ent_repo.apply_ner_purge.assert_not_called()


def test_purge_ner_terms_applies_the_plan_and_reports_the_ledger(mocker: MockerFixture) -> None:
    """The write consumes the same plan the preview showed and never runs on an empty plan."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    plan = NerPurgePlan(
        excluded_terms=["iptu"],
        items=[NerPurgeItem(entity_id=11, name="iptu", entity_type="ORG", excluded_term="iptu")],
    )
    mock_ent_repo.plan_ner_purge.return_value = plan
    mock_ent_repo.apply_ner_purge.return_value = NerPurgeResult(entities_deleted=1, purge_ids=[7])

    result = EntityService(mock_ent_repo).purge_ner_terms()

    assert result.entities_deleted == 1
    assert result.purge_ids == [7]
    mock_ent_repo.apply_ner_purge.assert_called_once()
    assert mock_ent_repo.apply_ner_purge.call_args.args[0] is plan


def test_purge_ner_terms_writes_nothing_when_nothing_matches(mocker: MockerFixture) -> None:
    """An empty plan is not a write: no ledger row is claimed for a purge that deleted nothing."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.plan_ner_purge.return_value = NerPurgePlan()

    result = EntityService(mock_ent_repo).purge_ner_terms()

    assert result.entities_deleted == 0
    assert result.purge_ids == []
    mock_ent_repo.apply_ner_purge.assert_not_called()


def test_remove_ner_exclusions_ignores_blank_input(mocker: MockerFixture) -> None:
    """Nothing is deleted when the caller sends only whitespace."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    service = EntityService(mock_ent_repo)

    assert service.remove_ner_exclusions(["  "]) == 0

    mock_ent_repo.remove_ner_exclusions.assert_not_called()
