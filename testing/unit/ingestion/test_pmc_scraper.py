from unittest.mock import Mock

import pytest
import requests
from pytest_mock import MockerFixture

from scrinalia.domains.ingestion.adapters.pmc_scraper import PMCScraperAdapter
from scrinalia.domains.ingestion.ports import AdapterFatalError, AdapterNetworkError, AdapterNotFoundError, SourceConfig

# ==========================================
# PMC SCRAPER ADAPTER TESTS (HTTP SCRAPER)
# ==========================================

#: The origin the adapter is pointed at. It arrives as configuration now, so the test states it
#: instead of relying on the environment — and the adapter never reads ``settings``.
SOURCE = SourceConfig(
    base_url="https://arquivos.curitiba.pr.gov.br/resultado?pagina=",
    detail_url="https://arquivos.curitiba.pr.gov.br/detalhe?id=",
)


def _adapter() -> PMCScraperAdapter:
    return PMCScraperAdapter(SOURCE)


def test_fetch_details_success(mocker: MockerFixture, html_mock_valid: str) -> None:
    """Guarantees the correct extraction of a valid HTML."""
    mock_response = Mock()
    mock_response.text = html_mock_valid
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    # Intercepts 'requests' directly inside the adapter file
    mocker.patch("scrinalia.domains.ingestion.adapters.pmc_scraper.requests.get", return_value=mock_response)

    adapter = _adapter()
    result = adapter.fetch_details("doc-123")

    assert result["title"] == "Inventario e Avaliações do Matadouro Modelo Atuba"
    assert (
        result["attch_down_link"]
        == "https://arquivos.curitiba.pr.gov.br/servidorArquivos/api/documento/visualizar/7UWlwHtkdzmeT5iV5XpSo4Tr"
    )
    assert "_url_origem" in result


def test_fetch_details_ignores_empty(mocker: MockerFixture, html_mock_empty: str) -> None:
    """Guarantees that tags not filled in the HTML do not pollute the dictionary with empty keys."""
    mock_response = Mock()
    mock_response.text = html_mock_empty
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    mocker.patch("scrinalia.domains.ingestion.adapters.pmc_scraper.requests.get", return_value=mock_response)

    adapter = _adapter()
    result = adapter.fetch_details("doc-404-fake")

    assert len(result) == 1
    assert "_url_origem" in result
    assert "title" not in result


def test_fetch_details_404_raises_domain_exception(mocker: MockerFixture) -> None:
    """Guarantees that a 404 from requests is translated into AdapterNotFoundError."""
    mock_response = Mock()
    mock_response.status_code = 404

    http_error = requests.exceptions.HTTPError("404 Not Found", response=mock_response)

    mocker.patch("scrinalia.domains.ingestion.adapters.pmc_scraper.requests.get", side_effect=http_error)

    adapter = _adapter()

    # Validates whether the adapter converted the error correctly
    with pytest.raises(AdapterNotFoundError) as exc_info:
        adapter.fetch_details("doc-inexistente")

    assert "does not exist" in str(exc_info.value)


def test_fetch_details_network_error_raises_domain_exception(mocker: MockerFixture) -> None:
    """Guarantees that Timeouts or internet drops become AdapterNetworkError."""
    timeout_error = requests.exceptions.Timeout("Read timeout")

    mocker.patch("scrinalia.domains.ingestion.adapters.pmc_scraper.requests.get", side_effect=timeout_error)

    adapter = _adapter()

    with pytest.raises(AdapterNetworkError):
        adapter.fetch_details("doc-123")


def test_fetch_details_fatal_error_raises_domain_exception(mocker: MockerFixture) -> None:
    """Guarantees that any unexpected error or layout break in parsing becomes AdapterFatalError."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    # We simulate a catastrophic failure: when trying to read .text, Python throws a generic error
    # This goes straight to your adapter's 'except Exception' block
    type(mock_response).text = mocker.PropertyMock(side_effect=ValueError("HTML layout changed completely"))

    mocker.patch("scrinalia.domains.ingestion.adapters.pmc_scraper.requests.get", return_value=mock_response)

    adapter = _adapter()

    with pytest.raises(AdapterFatalError) as exc_info:
        adapter.fetch_details("doc-123")

    assert "Error parsing the HTML" in str(exc_info.value)
