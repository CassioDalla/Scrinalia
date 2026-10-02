from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.repository import DocumentRepository


def test_stamp_ai_execution_updates_jsonb(mocker: MockerFixture) -> None:
    """Guarantees that the function marks the execution log without deleting old keys."""
    mock_db = mocker.Mock(spec=Session)

    # Creates a fake document with an existing log
    fake_doc = mocker.Mock()
    fake_doc.execution_log = {"migracao_base": "DONE"}

    # Simulates select() finding the document
    mock_db.execute.return_value.scalar_one_or_none.return_value = fake_doc

    # Intercepts the SQLAlchemy function that warns about changes to the JSON
    mock_flag = mocker.patch("domains.archive.repository.document_repo.flag_modified")

    repo = DocumentRepository(mock_db)
    repo.stamp_ai_execution("doc-123", "ner_spacy_v1")

    # The JSONB must have preserved the old value and added the new one
    assert fake_doc.execution_log == {"migracao_base": "DONE", "ner_spacy_v1": "DONE"}
    mock_flag.assert_called_once_with(fake_doc, "execution_log")


def test_stamp_ai_execution_ignores_missing_doc(mocker: MockerFixture) -> None:
    """Sad Path: If the document does not exist, the function must return silently."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    mock_flag = mocker.patch("domains.archive.repository.document_repo.flag_modified")

    repo = DocumentRepository(mock_db)
    repo.stamp_ai_execution("doc-fantasma", "ner")

    mock_flag.assert_not_called()


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
