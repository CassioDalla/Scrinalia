from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.repository.typology_repo import TypologyRepository


def test_get_active_typologies_formats_context_label_correctly(mocker: MockerFixture) -> None:
    """Guarantees that the returned dictionary formats the context label for the AI."""
    mock_db = mocker.Mock(spec=Session)
    repo = TypologyRepository(mock_db)

    # Return tuples: (id, name, description)
    mock_db.execute.return_value.all.return_value = [
        (1, "Fotografia", "Imagens estáticas e rolos."),
        (2, "Planta", None),  # Testing the fallback without description
    ]

    result = repo.get_active_typologies()

    # Validations
    assert isinstance(result, dict)
    assert len(result) == 2

    # Case 1: Name + Description
    assert "Fotografia: Imagens estáticas e rolos." in result
    assert result["Fotografia: Imagens estáticas e rolos."] == 1

    # Case 2: Name only (Fallback)
    assert "Planta" in result
    assert result["Planta"] == 2
