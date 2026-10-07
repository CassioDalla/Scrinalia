import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import InvalidParam
from scrinalia.domains.archive.repository import EntityRepository
from scrinalia.domains.archive.schemas import ResolveConflictCommand
from scrinalia.domains.archive.schemas.entity_schema import (
    ConflictResolutionData,
    ConflictResolutionPlan,
    CrossDomainConflict,
    CrossDomainConflictPage,
)
from scrinalia.domains.archive.services import EntityService

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
    ``pair_kind`` is the lever that separates 122 spelling questions from 5 050 structural ones.

    It is not called ``scope``: Litestar reserves that name for the ASGI scope, and a handler
    parameter with it silently receives the raw request instead of the query string.
    """
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.page_cross_domain_conflicts.return_value = CrossDomainConflictPage(total=0, limit=50, offset=0)

    service = EntityService(mock_ent_repo)
    service.page_cross_domain_conflicts(threshold=0.9, pair_kind="near_duplicate", limit=10, offset=20)

    mock_ent_repo.page_cross_domain_conflicts.assert_called_once_with(
        threshold=0.9, pair_kind="near_duplicate", limit=10, offset=20
    )


# ==========================================
# TESTS: NER EXCLUSIONS
# ==========================================


def test_exclude_terms_from_ner_records_and_purges(mocker: MockerFixture) -> None:
    """The decision is durable *and* retroactive: it bans the term and wipes past entities."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.delete_entities_by_names.return_value = 3

    service = EntityService(mock_ent_repo)
    deleted = service.exclude_terms_from_ner([" IPTU ", "iptu"], reason="assunto, não entidade", tag_id=7)

    assert deleted == 3
    mock_ent_repo.add_ner_exclusions.assert_called_once_with(
        ["iptu", "iptu"], source="HUMAN", reason="assunto, não entidade", tag_id=7
    )
    mock_ent_repo.delete_entities_by_names.assert_called_once_with(["iptu", "iptu"])


def test_exclude_terms_from_ner_ignores_blank_input(mocker: MockerFixture) -> None:
    """A blank term must not reach the catalog nor trigger a purge."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    service = EntityService(mock_ent_repo)

    assert service.exclude_terms_from_ner(["   ", ""]) == 0

    mock_ent_repo.add_ner_exclusions.assert_not_called()
    mock_ent_repo.delete_entities_by_names.assert_not_called()


def test_exclude_terms_from_ner_defaults_to_human_source(mocker: MockerFixture) -> None:
    """Without an explicit source the decision is attributed to the curator."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.delete_entities_by_names.return_value = 0

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


def test_remove_ner_exclusions_ignores_blank_input(mocker: MockerFixture) -> None:
    """Nothing is deleted when the caller sends only whitespace."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    service = EntityService(mock_ent_repo)

    assert service.remove_ner_exclusions(["  "]) == 0

    mock_ent_repo.remove_ner_exclusions.assert_not_called()
