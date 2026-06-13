import requests
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from core.crud import queue_crud, staging_crud
from core.models.queue import ScrapeStatus, ScrapingQueue
from scripts.staging import scrape_descriptions_details


def mock_http_404_error(*args, **kwargs) -> None:
    response = requests.Response()
    response.status_code = 404
    raise requests.exceptions.HTTPError("404 Not Found", response=response)


def test_process_batch_sucesso(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)

    # Mocks baseados puramente em objetos importados
    mocker.patch.object(scrape_descriptions_details, "fetch_and_parse_html", return_value={"title": "Teste"})
    mock_staging = mocker.patch.object(staging_crud, "save_scraped_description")
    mock_queue = mocker.patch.object(queue_crud, "update_queue_status")

    scrape_descriptions_details.process_scraping_batch(mock_db, [fila_mock])

    mock_staging.assert_called_once_with(mock_db, "doc-123", {"title": "Teste"})
    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.DONE)


def test_process_batch_erro_404(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)

    mocker.patch.object(scrape_descriptions_details, "fetch_and_parse_html", side_effect=mock_http_404_error)
    mock_staging = mocker.patch.object(staging_crud, "save_scraped_description")
    mock_queue = mocker.patch.object(queue_crud, "update_queue_status")

    scrape_descriptions_details.process_scraping_batch(mock_db, [fila_mock])

    mock_staging.assert_not_called()
    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.NOT_FOUND, error_msg="404 Not Found")


def test_process_batch_timeout_retry(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)

    mocker.patch.object(
        scrape_descriptions_details, "fetch_and_parse_html", side_effect=requests.exceptions.Timeout("Timeout")
    )
    mock_queue = mocker.patch.object(queue_crud, "update_queue_status")

    scrape_descriptions_details.process_scraping_batch(mock_db, [fila_mock])

    mock_queue.assert_called_once_with(
        mock_db, "doc-123", ScrapeStatus.NETWORK_ERROR, error_msg="Timeout", increment_retry=True
    )


def test_process_batch_max_retries_excedido(mocker: MockerFixture, fila_mock: ScrapingQueue) -> None:
    fila_mock.retry_count = 3
    mock_db = mocker.Mock(spec=Session)

    mocker.patch.object(
        scrape_descriptions_details,
        "fetch_and_parse_html",
        side_effect=requests.exceptions.ConnectionError("Caiu a rede"),
    )
    mock_queue = mocker.patch.object(queue_crud, "update_queue_status")

    scrape_descriptions_details.process_scraping_batch(mock_db, [fila_mock])

    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.FATAL_ERROR, error_msg="Caiu a rede")
