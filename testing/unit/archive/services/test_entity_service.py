import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from memoria_curitibana.domains.archive.repository import EntityRepository
from memoria_curitibana.domains.archive.schemas import ResolveConflictCommand
from memoria_curitibana.domains.archive.schemas.entity_schema import CrossDomainConflict
from memoria_curitibana.domains.archive.services import EntityService

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


def test_resolve_cross_domain_conflict_success(mocker: MockerFixture) -> None:
    """Happy path: Confirms the forwarding of the atomic instruction to the repository."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)

    mock_ent_repo.resolve_cross_domain_conflict.return_value = 5  # 5 documents transferred

    service = EntityService(mock_ent_repo)
    command = ResolveConflictCommand(winner="ENTITY", tag_id=10, entity_id=20)
    result = service.resolve_cross_domain_conflict(command)

    # The provenance of the decision travels with it: the catalog records who decided.
    mock_ent_repo.resolve_cross_domain_conflict.assert_called_once_with("ENTITY", 10, 20, source="HUMAN")
    assert result.winner == "ENTITY"
    assert result.documents_transferred == 5


def test_resolve_cross_domain_conflict_forwards_judge_source(mocker: MockerFixture) -> None:
    """The LLM judge must be recorded as the author of the decision, not the curator."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    mock_ent_repo.resolve_cross_domain_conflict.return_value = 0

    service = EntityService(mock_ent_repo)
    service.resolve_cross_domain_conflict(ResolveConflictCommand(winner="TAG", tag_id=1, entity_id=2), source="JUDGE")

    mock_ent_repo.resolve_cross_domain_conflict.assert_called_once_with("TAG", 1, 2, source="JUDGE")


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
