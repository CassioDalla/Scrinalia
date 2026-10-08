from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from scrinalia.domains.archive.repository.tag_repo import TagRepository


def test_save_stopwords_ignores_empty_or_dirty_list(mocker: MockerFixture) -> None:
    """Guarantees that blank strings or empty lists do not generate useless queries."""
    mock_db = mocker.Mock(spec=Session)
    repo = TagRepository(mock_db)

    # None of the words is valid
    result = repo.save_stopwords(["   ", ""])

    assert result == 0
    mock_db.execute.assert_not_called()


def test_fetch_tags_for_clustering_ignores_numbers(mocker: MockerFixture) -> None:
    """Guarantees that the repository filters tags that are only numbers or numbers with dots."""
    mock_db = mocker.Mock(spec=Session)
    repo = TagRepository(mock_db)

    # Simulate the database return with useful words and numeric noise
    mock_db.scalars.return_value.all.return_value = ["urbano", "123", "ruas", "1.500", None]

    result = repo.fetch_tags_for_clustering()

    # Must ignore "123", "1.500" and None
    assert result == ["urbano", "ruas"]


def test_get_synonyms_mapping_ignores_empty_list(mocker: MockerFixture) -> None:
    """Sad Path: Avoids a database round trip if there are no words to look up."""
    mock_db = mocker.Mock(spec=Session)
    repo = TagRepository(mock_db)

    result = repo.get_synonyms_mapping([])

    assert result == {}
    mock_db.execute.assert_not_called()


def test_get_synonyms_mapping_returns_dictionary(mocker: MockerFixture) -> None:
    """Guarantees that the SQL response is converted into a perfect mapping dictionary."""
    mock_db = mocker.Mock(spec=Session)
    repo = TagRepository(mock_db)

    row1 = mocker.Mock(synonym_name="prefeitura", canonical_tag_id=10)
    row2 = mocker.Mock(synonym_name="governo", canonical_tag_id=15)

    mock_db.execute.return_value.all.return_value = [row1, row2]

    result = repo.get_synonyms_mapping(["prefeitura", "governo"])

    assert result == {"prefeitura": 10, "governo": 15}
