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

    mock_ent_repo.resolve_cross_domain_conflict.assert_called_once_with("ENTITY", 10, 20)
    assert result.winner == "ENTITY"
    assert result.documents_transferred == 5
