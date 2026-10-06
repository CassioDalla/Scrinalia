from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.repository.typology_repo import TypologyRepository


def test_get_active_typologies_uses_bare_names_as_labels(mocker: MockerFixture) -> None:
    """
    The returned dictionary maps the bare typology name to its id.

    Regression: the label used to be ``"Name: description"``. Measured on the real model,
    appending the context makes mDeBERTa lose the entailment as the label grows and end on
    a confident wrong typology, so a filled ``context_description`` silently degraded
    classification. The label must stay bare.
    """
    mock_db = mocker.Mock(spec=Session)
    repo = TypologyRepository(mock_db)

    # The query now selects only (id, name).
    mock_db.execute.return_value.all.return_value = [
        (1, "Fotografia"),
        (2, "Planta"),
    ]

    result = repo.get_active_typologies()

    assert isinstance(result, dict)
    assert result == {"Fotografia": 1, "Planta": 2}
    assert all(":" not in label for label in result)


def test_get_active_typologies_does_not_select_the_context_column(mocker: MockerFixture) -> None:
    """The context must not even reach the classifier payload."""
    mock_db = mocker.Mock(spec=Session)
    repo = TypologyRepository(mock_db)
    mock_db.execute.return_value.all.return_value = []

    repo.get_active_typologies()

    compiled = str(mock_db.execute.call_args[0][0])
    assert "context_description" not in compiled
    assert "name" in compiled


def test_get_active_typologies_filters_on_the_retirement_flag(mocker: MockerFixture) -> None:
    """
    ``is_active`` is the filter that reaches the classifier.

    Without it in the query, retiring a typology would be a change the archivist sees on the screen
    and the model never hears about — it would keep proposing the spelling the catalogue decided
    against. The column is asserted in the compiled statement because the predicate is the whole
    point of the flag.
    """
    mock_db = mocker.Mock(spec=Session)
    repo = TypologyRepository(mock_db)
    mock_db.execute.return_value.all.return_value = []

    repo.get_active_typologies()

    compiled = str(mock_db.execute.call_args[0][0])
    assert "is_active" in compiled
