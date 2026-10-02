from unittest.mock import MagicMock, patch

import pytest

from core.llm_clients.ollama_client import OllamaClient


def test_ollama_client_empty_prompt_raises_error():
    client = OllamaClient()

    # Checks whether ValueError is raised with the correct message
    with pytest.raises(ValueError, match="não pode ser uma string vazia"):
        client.generate_json("")

    with pytest.raises(ValueError):
        client.generate_json("   \n  ")  # Tests whitespace only


@patch("core.llm_clients.ollama_client.requests.post")
def test_ollama_client_success_returns_json_string(mock_post):
    # Prepare the requests "stub" to return a fake success response
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": '{"label": "Contrato", "score": 0.95}'}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    client = OllamaClient(host="http://teste.local")
    result = client.generate_json("Classifique o documento XPTO")

    # Checks whether the client processed the response correctly
    assert result == '{"label": "Contrato", "score": 0.95}'
    # Checks whether the payload sent contained the correct data
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["prompt"] == "Classifique o documento XPTO"


@patch("core.llm_clients.ollama_client.requests.post")
def test_ollama_client_network_failure_returns_empty_dict(mock_post):
    # Simulates a Timeout error
    mock_post.side_effect = Exception("Timeout na rede")

    client = OllamaClient()
    result = client.generate_json("Teste")
    assert result == {}
