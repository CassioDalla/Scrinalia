from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.repository import EntityRepository


def test_get_or_create_entities_ignores_empty_list(mocker: MockerFixture) -> None:
    """Guarantees that the repository does not hit the database needlessly if there are no entities."""
    mock_db = mocker.Mock(spec=Session)
    repo = EntityRepository(mock_db)

    result = repo.get_or_create_entities([])

    assert result == []
    mock_db.execute.assert_not_called()


def test_get_or_create_entities_happy_path(mocker: MockerFixture) -> None:
    """Guarantees that the function processes DTOs, trims whitespace and calls bulk INSERT/SELECT."""
    mock_db = mocker.Mock(spec=Session)
    repo = EntityRepository(mock_db)

    # Creating fake DTOs
    ent1 = mocker.Mock(name=" Winston Churchill  ", entity_type="PER")
    ent2 = mocker.Mock(name="Curitiba", entity_type="LOC")

    # Simulate that the database returned IDs 1 and 2
    mock_db.scalars.return_value.all.return_value = [1, 2]

    result = repo.get_or_create_entities([ent1, ent2])

    assert result == [1, 2]
    # Guarantees that there was one execute (for the insert) and one scalars (for the select)
    assert mock_db.execute.call_count == 1
    assert mock_db.scalars.call_count == 1


def test_purge_orphan_entities_ignores_when_none(mocker: MockerFixture) -> None:
    """Guarantees that there is no DELETE execute if no orphans are found."""
    mock_db = mocker.Mock(spec=Session)
    repo = EntityRepository(mock_db)

    # Simulate that the orphan search returned empty
    mock_db.scalars.return_value.all.return_value = []

    deleted_count = repo.purge_orphan_entities()

    assert deleted_count == 0
    # mock_db.execute would only be called on DELETE. Since it was avoided, call_count == 0
    assert mock_db.execute.call_count == 0


def test_purge_orphan_entities_deletes_found_orphans(mocker: MockerFixture) -> None:
    """Guarantees that DELETE is called if orphans exist."""
    mock_db = mocker.Mock(spec=Session)
    repo = EntityRepository(mock_db)

    # Simulate orphan ids
    mock_db.scalars.return_value.all.return_value = [10, 20]
    # Simulate the delete rowcount return
    mock_db.execute.return_value.rowcount = 2

    deleted_count = repo.purge_orphan_entities()

    assert deleted_count == 2
    assert mock_db.execute.call_count == 1  # Called the delete
