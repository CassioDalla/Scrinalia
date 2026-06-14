from unittest.mock import Mock

import pytest
import requests
from pytest_mock import MockerFixture

from domains.ingestion.adapters.pmc_scraper import PMCScraperAdapter
from domains.ingestion.ports import AdapterFatalError, AdapterNetworkError, AdapterNotFoundError

# ==========================================
# TESTES DO ADAPTADOR ARQDOC (SCRAPER HTTP)
# ==========================================


def test_fetch_details_sucesso(mocker: MockerFixture, html_mock_valido: str) -> None:
    """Garante a extração correta de um HTML válido."""
    mock_response = Mock()
    mock_response.text = html_mock_valido
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    # Intercepta o 'requests' diretamente dentro do arquivo do adaptador
    mocker.patch("domains.ingestion.adapters.pmc_scraper.requests.get", return_value=mock_response)

    adapter = PMCScraperAdapter()
    resultado = adapter.fetch_details("doc-123")

    assert resultado["title"] == "Inventario e Avaliações do Matadouro Modelo Atuba"
    assert (
        resultado["attch_down_link"]
        == "https://arquivos.curitiba.pr.gov.br/servidorArquivos/api/documento/visualizar/7UWlwHtkdzmeT5iV5XpSo4Tr"
    )
    assert "_url_origem" in resultado


def test_fetch_details_ignora_vazios(mocker: MockerFixture, html_mock_vazio: str) -> None:
    """Garante que tags não preenchidas no HTML não sujam o dicionário com chaves vazias."""
    mock_response = Mock()
    mock_response.text = html_mock_vazio
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    mocker.patch("domains.ingestion.adapters.pmc_scraper.requests.get", return_value=mock_response)

    adapter = PMCScraperAdapter()
    resultado = adapter.fetch_details("doc-404-fake")

    assert len(resultado) == 1
    assert "_url_origem" in resultado
    assert "title" not in resultado


def test_fetch_details_erro_404_lanca_excecao_de_dominio(mocker: MockerFixture) -> None:
    """Garante que um 404 do requests é traduzido para AdapterNotFoundError."""
    mock_response = Mock()
    mock_response.status_code = 404

    erro_http = requests.exceptions.HTTPError("404 Not Found", response=mock_response)

    mocker.patch("domains.ingestion.adapters.pmc_scraper.requests.get", side_effect=erro_http)

    adapter = PMCScraperAdapter()

    # Valida se o adaptador converteu o erro corretamente
    with pytest.raises(AdapterNotFoundError) as exc_info:
        adapter.fetch_details("doc-inexistente")

    assert "não existe" in str(exc_info.value)


def test_fetch_details_erro_de_rede_lanca_excecao_de_dominio(mocker: MockerFixture) -> None:
    """Garante que Timeouts ou quedas de internet viram AdapterNetworkError."""
    erro_timeout = requests.exceptions.Timeout("Read timeout")

    mocker.patch("domains.ingestion.adapters.pmc_scraper.requests.get", side_effect=erro_timeout)

    adapter = PMCScraperAdapter()

    with pytest.raises(AdapterNetworkError):
        adapter.fetch_details("doc-123")


def test_fetch_details_erro_fatal_lanca_excecao_de_dominio(mocker: MockerFixture) -> None:
    """Garante que qualquer erro inesperado ou quebra de layout no parsing vira AdapterFatalError."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()

    # Simulamos uma falha catastrófica: ao tentar ler o .text, o Python dispara um erro genérico
    # Isso vai direto para o bloco 'except Exception' do seu adaptador
    type(mock_response).text = mocker.PropertyMock(side_effect=ValueError("Layout do HTML mudou completamente"))

    mocker.patch("domains.ingestion.adapters.pmc_scraper.requests.get", return_value=mock_response)

    adapter = PMCScraperAdapter()

    with pytest.raises(AdapterFatalError) as exc_info:
        adapter.fetch_details("doc-123")

    assert "Erro ao fazer o parse do HTML" in str(exc_info.value)
