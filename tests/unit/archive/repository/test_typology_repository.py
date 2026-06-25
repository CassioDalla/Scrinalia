from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.repository.typology_repo import TypologyRepository


def test_get_active_typologies_formata_context_label_corretamente(mocker: MockerFixture) -> None:
    """Garante que o dicionário retornado formata a label de contexto para a IA."""
    mock_db = mocker.Mock(spec=Session)
    repo = TypologyRepository(mock_db)

    # Tuplas de retorno: (id, name, description)
    mock_db.execute.return_value.all.return_value = [
        (1, "Fotografia", "Imagens estáticas e rolos."),
        (2, "Planta", None),  # Testando o fallback sem descrição
    ]

    resultado = repo.get_active_typologies()

    # Validações
    assert isinstance(resultado, dict)
    assert len(resultado) == 2

    # Caso 1: Nome + Descrição
    assert "Fotografia: Imagens estáticas e rolos." in resultado
    assert resultado["Fotografia: Imagens estáticas e rolos."] == 1

    # Caso 2: Somente Nome (Fallback)
    assert "Planta" in resultado
    assert resultado["Planta"] == 2
