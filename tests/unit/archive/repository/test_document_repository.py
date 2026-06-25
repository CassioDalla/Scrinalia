from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.repository import DocumentRepository


def test_stamp_ai_execution_atualiza_jsonb(mocker: MockerFixture) -> None:
    """Garante que a função marca o log de execução sem apagar chaves antigas."""
    mock_db = mocker.Mock(spec=Session)

    # Cria um documento fake com um log existente
    doc_fake = mocker.Mock()
    doc_fake.execution_log = {"migracao_base": "DONE"}

    # Simula o select() encontrando o documento
    mock_db.execute.return_value.scalar_one_or_none.return_value = doc_fake

    # Intercepta a função do SQLAlchemy que avisa sobre mudança no JSON
    mock_flag = mocker.patch("domains.archive.repository.document_repo.flag_modified")

    repo = DocumentRepository(mock_db)
    repo.stamp_ai_execution("doc-123", "ner_spacy_v1")

    # O JSONB deve ter preservado o antigo e adicionado o novo
    assert doc_fake.execution_log == {"migracao_base": "DONE", "ner_spacy_v1": "DONE"}
    mock_flag.assert_called_once_with(doc_fake, "execution_log")


def test_stamp_ai_execution_ignora_doc_nao_encontrado(mocker: MockerFixture) -> None:
    """Caminho Triste: Se o documento não existir, a função deve retornar silenciosamente."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    mock_flag = mocker.patch("domains.archive.repository.document_repo.flag_modified")

    repo = DocumentRepository(mock_db)
    repo.stamp_ai_execution("doc-fantasma", "ner")

    mock_flag.assert_not_called()


def test_fetch_documents_for_clustering_happy_path(mocker: MockerFixture) -> None:
    """Garante que as colunas são concatenadas perfeitamente, removendo excesso de espaços."""
    mock_db = mocker.Mock(spec=Session)

    doc1 = mocker.Mock(
        original_title=" Título  com    espaços ",
        scope_content="Descrição válida",
        admin_bio_history=None,  # Deve ignorar
    )
    doc2 = mocker.Mock(original_title="Sem descrição", scope_content=None, admin_bio_history=None)

    mock_db.scalars.return_value.all.return_value = [doc1, doc2]

    repo = DocumentRepository(mock_db)
    resultado = repo.fetch_documents_for_clustering(["original_title", "scope_content", "admin_bio_history"])

    # Validações: Limpou espaços, concatenou com '. ' e ignorou colunas None
    assert len(resultado) == 2
    assert resultado[0] == "Título com espaços. Descrição válida."
    assert resultado[1] == "Sem descrição."
