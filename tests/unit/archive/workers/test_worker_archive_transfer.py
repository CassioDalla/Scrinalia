from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive import repository
from domains.archive.schemas import ArchiveDocumentDTO
from domains.archive.workers import worker_archive_transfer

# ==========================================
# TESTES DE ORQUESTRAÇÃO E TRANSAÇÃO (Transferência)
# ==========================================


def test_run_archive_transfer_fluxo_completo(mocker: MockerFixture, mock_staging_doc) -> None:
    """Testa o caminho feliz, onde um documento inédito da Staging é inserido na Archive."""
    mock_db = mocker.Mock(spec=Session)

    # Intercepta as conexões de banco
    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Intercepta o Serviço de Tags
    mock_tag_service = mocker.patch("domains.archive.workers.worker_archive_transfer.TagService")
    mock_tag_service_instance = mock_tag_service.return_value
    mock_tag_service_instance.extract_and_clean_tags.return_value = [mocker.Mock()]

    # Usa a fábrica do conftest para gerar o doc perfeito!
    doc_staging = mock_staging_doc(description_id="doc-100", raw_content_hash="hash_123")

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_staging]

    # Intercepta o repositório com O NOME CORRETO DA FUNÇÃO
    mock_upsert = mocker.patch.object(repository, "upsert_archive_document", return_value=True)
    _mock_tags = mocker.patch.object(repository, "get_or_create_tags", return_value=[99])
    _mock_link = mocker.patch.object(repository, "link_description_relationships")

    # Executa
    worker_archive_transfer.execute(mock_db)

    # Validação
    assert mock_upsert.call_count == 1
    args, _ = mock_upsert.call_args
    dto_enviado: ArchiveDocumentDTO = args[1]

    assert dto_enviado.description_id == "doc-100"
    assert dto_enviado.staging_content_hash == "hash_123"
    assert dto_enviado.execution_log == {}

    mock_db.commit.assert_called_once()


def test_run_archive_transfer_idempotencia(mocker: MockerFixture, mock_staging_doc) -> None:
    """Testa a Carga Incremental: Se o Hash for igual, o Upsert retorna False e o pipeline pula o documento."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Usa a fábrica novamente!
    doc_staging = mock_staging_doc()

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_staging]

    mock_tag_service = mocker.patch("domains.archive.workers.worker_archive_transfer.TagService")

    # Simulamos o bloqueio no upsert
    mock_upsert = mocker.patch.object(repository, "upsert_archive_document", return_value=False)
    mock_tags = mocker.patch.object(repository, "get_or_create_tags")
    mock_link = mocker.patch.object(repository, "link_description_relationships")

    # Executa
    worker_archive_transfer.execute(mock_db)

    # Validações
    mock_upsert.assert_called_once()
    mock_tag_service.return_value.extract_and_clean_tags.assert_not_called()
    mock_tags.assert_not_called()
    mock_link.assert_not_called()

    mock_db.commit.assert_called_once()
