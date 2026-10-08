from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from scrinalia.domains.archive.repository import DocumentRepository


def test_fetch_documents_for_clustering_happy_path(mocker: MockerFixture) -> None:
    """Guarantees that the columns are perfectly concatenated, removing excess whitespace."""
    mock_db = mocker.Mock(spec=Session)

    doc1 = mocker.Mock(
        original_title=" Título  com    espaços ",
        scope_content="Descrição válida",
        admin_bio_history=None,  # Must be ignored
    )
    doc2 = mocker.Mock(original_title="Sem descrição", scope_content=None, admin_bio_history=None)

    mock_db.scalars.return_value.all.return_value = [doc1, doc2]

    repo = DocumentRepository(mock_db)
    result = repo.fetch_documents_for_clustering(["original_title", "scope_content", "admin_bio_history"])

    # Validations: Trimmed whitespace, concatenated with '. ' and ignored None columns
    assert len(result) == 2
    assert result[0] == "Título com espaços. Descrição válida."
    assert result[1] == "Sem descrição."
