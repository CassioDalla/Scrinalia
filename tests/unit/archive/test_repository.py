from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive import repository

# TODO REFATORAR TESTES UNITARIOSS PARA TESTAR CADA REPOSITORIO


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

    repository.stamp_ai_execution(mock_db, "doc-123", "ner_spacy_v1")

    # O JSONB deve ter preservado o antigo e adicionado o novo
    assert doc_fake.execution_log == {"migracao_base": "DONE", "ner_spacy_v1": "DONE"}
    mock_flag.assert_called_once_with(doc_fake, "execution_log")


def test_get_or_create_entities_ignora_lista_vazia(mocker: MockerFixture) -> None:
    """Garante que o repositório não bate no banco atoa se não houver entidades."""
    mock_db = mocker.Mock(spec=Session)

    resultado = repository.get_or_create_entities(mock_db, [])

    assert resultado == []
    mock_db.execute.assert_not_called()


def test_save_stopwords_ignora_lista_vazia_ou_suja(mocker: MockerFixture) -> None:
    """Garante que espaços em branco ou listas vazias não geram queries inúteis."""
    mock_db = mocker.Mock(spec=Session)

    repository.save_stopwords(mock_db, ["   ", ""])

    mock_db.execute.assert_not_called()
