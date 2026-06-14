from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.ingestion import repository, worker
from domains.ingestion.models import ScrapeStatus, ScrapingQueue
from domains.ingestion.ports import (
    AdapterFatalError,
    AdapterNetworkError,
    AdapterNotFoundError,
    IDetailAdapter,
)

# ==========================================
# TESTES DO ORQUESTRADOR DA INGESTÃO (WORKER)
# ==========================================


def test_run_detail_scraping_job_sucesso(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)

    # 1. Isola a busca da fila para retornar apenas o mock
    mocker.patch.object(repository, "get_from_queue", return_value=[fila_mock])

    # 2. Cria o mock do Adaptador respeitando a Interface
    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.return_value = {"title": "Teste"}

    # 3. Isola a persistência
    mock_save = mocker.patch.object(repository, "save_raw_data")
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    # 4. Executa o Worker injetando as dependências
    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    # 5. Valida a orquestração
    mock_adapter.fetch_details.assert_called_once_with("doc-123")
    mock_save.assert_called_once_with(mock_db, "doc-123", {"title": "Teste"})
    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.DONE)


def test_run_detail_scraping_job_not_found(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)

    mocker.patch.object(repository, "get_from_queue", return_value=[fila_mock])
    mock_save = mocker.patch.object(repository, "save_raw_data")
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.side_effect = AdapterNotFoundError("Não existe")

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    mock_save.assert_not_called()
    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.NOT_FOUND, error_msg="Não existe")


def test_run_detail_scraping_job_network_retry(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)
    fila_mock.retry_count = 1  # Ainda tem tentativas sobrando

    mocker.patch.object(repository, "get_from_queue", return_value=[fila_mock])
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.side_effect = AdapterNetworkError("Caiu a internet")

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    mock_queue.assert_called_once_with(
        mock_db, "doc-123", ScrapeStatus.NETWORK_ERROR, error_msg="Caiu a internet", increment_retry=True
    )


def test_run_detail_scraping_job_max_retries_excedido(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)
    fila_mock.retry_count = 3  # Limite estourado!

    mocker.patch.object(repository, "get_from_queue", return_value=[fila_mock])
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.side_effect = AdapterNetworkError("Caiu de novo")

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    # O Worker deve interceptar que passou de 3 e lançar como FATAL
    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.FATAL_ERROR, error_msg="Caiu de novo")


def test_run_detail_scraping_job_fatal_error_direto(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)
    # Mesmo na primeira tentativa (retry=0), se for um erro fatal, ele não pode tentar de novo
    fila_mock.retry_count = 0

    mocker.patch.object(repository, "get_from_queue", return_value=[fila_mock])
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    # Exemplo: O BeautifulSoup quebrou tentando ler uma tag inexistente
    mock_adapter.fetch_details.side_effect = AdapterFatalError("HTML Malformado")

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.FATAL_ERROR, error_msg="HTML Malformado")
