from unittest.mock import MagicMock, patch

import pytest

from core.llm_clients.ollama_client import OllamaClient


def test_ollama_client_prompt_vazio_estoura_erro():
    client = OllamaClient()

    # Verifica se o ValueError é levantado com a mensagem correta
    with pytest.raises(ValueError, match="não pode ser uma string vazia"):
        client.generate_json("")

    with pytest.raises(ValueError):
        client.generate_json("   \n  ")  # Testa apenas espaços


@patch("core.llm_clients.ollama_client.requests.post")
def test_ollama_client_sucesso_retorna_string_json(mock_post):
    # Prepara o "dublê" do requests para devolver uma resposta falsa de sucesso
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": '{"label": "Contrato", "score": 0.95}'}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    client = OllamaClient(host="http://teste.local")
    resultado = client.generate_json("Classifique o documento XPTO")

    # Verifica se o cliente processou a resposta corretamente
    assert resultado == '{"label": "Contrato", "score": 0.95}'
    # Verifica se o payload enviado tinha os dados corretos
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["prompt"] == "Classifique o documento XPTO"


@patch("core.llm_clients.ollama_client.requests.post")
def test_ollama_client_falha_de_rede_retorna_dicionario_vazio(mock_post):
    # Simula um erro de Timeout
    mock_post.side_effect = Exception("Timeout na rede")

    client = OllamaClient()
    resultado = client.generate_json("Teste")
    assert resultado == {}
