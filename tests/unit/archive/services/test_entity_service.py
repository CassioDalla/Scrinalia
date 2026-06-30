import pytest
from pytest_mock import MockerFixture

from domains.archive.exceptions import InvalidParam
from domains.archive.repository import EntityRepository
from domains.archive.schemas.entity_schema import CrossDomainConflict
from domains.archive.services import EntityService

# ==========================================
# TESTES: CROSS DOMAIN
# ==========================================


def test_find_cross_domain_conflicts(mocker: MockerFixture) -> None:
    """Garante que o serviço repassa o threshold correto para o repositório e mapeia os DTOs."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)

    # Simulando o retorno da query SQL (que devolve Tuplas/Rows)
    mock_row = CrossDomainConflict(
        tag_id=1, tag_name="Batel", entity_id=99, entity_name="Batel", entity_type="LOC", similarity=1.0
    )
    mock_ent_repo.get_cross_domain_conflicts.return_value = [mock_row]

    service = EntityService(
        mock_ent_repo,
    )
    resultados = service.find_cross_domain_conflicts(threshold=0.90)

    mock_ent_repo.get_cross_domain_conflicts.assert_called_once_with(0.90)
    assert len(resultados) == 1
    assert resultados[0].tag_name == "Batel"
    assert resultados[0].entity_type == "LOC"


def test_resolve_cross_domain_conflict_invalido(mocker: MockerFixture) -> None:
    """Garante que a API barra tentativas de enviar um vencedor inválido."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)
    service = EntityService(mock_ent_repo)

    with pytest.raises(InvalidParam) as exc_info:
        service.resolve_cross_domain_conflict("VENCEDOR_FALSO", tag_id=1, entity_id=2)  # type: ignore

    assert "obrigatoriamente 'TAG' ou 'ENTITY'" in str(exc_info.value)
    mock_ent_repo.resolve_cross_domain_conflict.assert_not_called()


def test_resolve_cross_domain_conflict_sucesso(mocker: MockerFixture) -> None:
    """Caminho feliz: Confirma o repasse da instrução atômica para o repositório."""
    mock_ent_repo = mocker.Mock(spec=EntityRepository)

    mock_ent_repo.resolve_cross_domain_conflict.return_value = 5  # 5 documentos transferidos

    service = EntityService(mock_ent_repo)
    resultado = service.resolve_cross_domain_conflict("ENTITY", tag_id=10, entity_id=20)

    mock_ent_repo.resolve_cross_domain_conflict.assert_called_once_with("ENTITY", 10, 20)
    assert resultado.winner == "ENTITY"
    assert resultado.documents_transferred == 5
