from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.workers import worker_thumbnail

# ==========================================
# 1. TESTES DE REDE E MEMÓRIA
# ==========================================


def test_download_image_to_memory_sucesso(mocker: MockerFixture) -> None:
    """Testa o download simulando uma resposta 200 HTTP e o processamento da PIL."""
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.content = b"fake_bytes"

    mocker.patch("requests.get", return_value=mock_response)

    # Finge que a PIL abriu a imagem com sucesso
    mock_image = mocker.Mock()
    mock_image.mode = "RGB"
    mocker.patch("PIL.Image.open", return_value=mock_image)

    resultado = worker_thumbnail.download_image_to_memory("http://site.com/img.png")

    assert resultado is not None
    # Verifica se a imagem foi salva no buffer de saída
    mock_image.save.assert_called_once()


def test_download_image_to_memory_falha_http(mocker: MockerFixture) -> None:
    """Garante que erros 404/500 da prefeitura não quebrem o worker."""
    mock_response = mocker.Mock()
    mock_response.status_code = 404
    mocker.patch("requests.get", return_value=mock_response)

    resultado = worker_thumbnail.download_image_to_memory("http://site.com/img.png")

    assert resultado is None


def test_download_image_to_memory_exception(mocker: MockerFixture) -> None:
    """Garante que quedas de rede (Timeout) sejam tratadas graciosamente."""
    mocker.patch("requests.get", side_effect=Exception("Connection Timeout"))

    resultado = worker_thumbnail.download_image_to_memory("http://site.com/img.png")

    assert resultado is None


# ==========================================
# 2. TESTES DE ORQUESTRAÇÃO
# ==========================================


def test_execute_worker_thumbnails_sucesso(mocker: MockerFixture) -> None:
    """Caminho feliz: Baixa a imagem, sobe pro Storage e salva a URI."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_thumbnail, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db

    # CORREÇÃO: MagicMock
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Cria documento fake pendente
    doc_fake = mocker.Mock()
    doc_fake.description_id = "doc-1"
    doc_fake.original_thumbnail_url = "http://link.com"
    doc_fake.storage_thumbnail_uri = None
    doc_fake.execution_log = {}

    mock_db.scalars.return_value.yield_per.return_value = [doc_fake]

    # Mocks das integrações externas (Rede e MinIO)
    mocker.patch.object(worker_thumbnail, "download_image_to_memory", return_value=b"bytes")

    mock_storage = mocker.patch("domains.archive.workers.worker_thumbnail.S3Storage")
    mock_storage.return_value.upload_file.return_value = "s3://bucket/thumb_doc-1.jpg"

    # Previne o sleep de atrasar os testes
    mocker.patch("time.sleep")

    worker_thumbnail.execute(mock_db)

    # Validações
    assert doc_fake.storage_thumbnail_uri == "s3://bucket/thumb_doc-1.jpg"
    mock_storage.return_value.upload_file.assert_called_once()
    mock_db.commit.assert_called_once()


def test_execute_worker_thumbnails_marca_falha_no_json(mocker: MockerFixture) -> None:
    """Se o download falhar, o worker deve marcar a falha no execution_log."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_thumbnail, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db

    # CORREÇÃO: MagicMock
    mock_db.begin_nested.return_value = mocker.MagicMock()

    doc_fake = mocker.Mock()
    doc_fake.original_thumbnail_url = "http://link-quebrado.com"
    doc_fake.execution_log = {}

    mock_db.scalars.return_value.yield_per.return_value = [doc_fake]

    # Força a falha no download
    mocker.patch.object(worker_thumbnail, "download_image_to_memory", return_value=None)
    mock_flag = mocker.patch("domains.archive.workers.worker_thumbnail.flag_modified")
    mocker.patch("time.sleep")

    worker_thumbnail.execute(mock_db)

    # O documento não recebe a URI, mas recebe a flag de falha
    assert doc_fake.execution_log == {"thumbnail_failed": "True"}
    mock_flag.assert_called_once_with(doc_fake, "execution_log")
    mock_db.commit.assert_called_once()
