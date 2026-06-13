from unittest.mock import Mock

from pytest_mock import MockerFixture

from scripts.staging import scrape_descriptions_details


def test_fetch_and_parse_html_sucesso(mocker: MockerFixture, html_mock_valido: str) -> None:
    mock_response = Mock()
    mock_response.text = html_mock_valido
    mock_response.raise_for_status = Mock()

    # Intercepta o método 'get' diretamente do objeto 'requests' importado no script
    mocker.patch.object(scrape_descriptions_details.requests, "get", return_value=mock_response)

    resultado = scrape_descriptions_details.fetch_and_parse_html("doc-123")

    assert resultado["title"] == "Inventario e Avaliações do Matadouro Modelo Atuba"
    assert (
        resultado["attch_down_link"]
        == "https://arquivos.curitiba.pr.gov.br/servidorArquivos/api/documento/visualizar/7UWlwHtkdzmeT5iV5XpSo4Tr"
    )
    assert "_url_origem" in resultado


def test_fetch_and_parse_html_ignora_vazios(mocker: MockerFixture, html_mock_vazio: str) -> None:
    mock_response = Mock()
    mock_response.text = html_mock_vazio
    mock_response.raise_for_status = Mock()

    mocker.patch.object(scrape_descriptions_details.requests, "get", return_value=mock_response)

    resultado = scrape_descriptions_details.fetch_and_parse_html("doc-404")

    assert len(resultado) == 1
    assert "_url_origem" in resultado
    assert "title" not in resultado
