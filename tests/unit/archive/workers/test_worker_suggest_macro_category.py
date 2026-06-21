import pandas as pd
import pytest

from domains.archive.engines.clustering import registry
from domains.archive.exceptions import InvalidParam
from domains.archive.workers.worker_suggest_macro_category import run_suggestion_engine


def test_worker_happy_path_formatting(mock_registry, mocker):
    """Garante que o worker formata o DataFrame do BERTopic para o DTO do Pydantic."""
    textos_analise = [f"texto_{i}" for i in range(15)]

    # Simula a saída do BERTopic
    mock_df = pd.DataFrame(
        [
            {"Topic": 0, "Count": 10, "Representation": ["urbano", "rua", "obras"]},
            {"Topic": 1, "Count": 5, "Representation": ["lei", "decreto", "oficio"]},
        ]
    )
    mock_topics = [0] * 10 + [1] * 5

    MockClass = mock_registry(registry)
    instancia_da_ia = MockClass.return_value
    instancia_da_ia.discover_topics.return_value = (mock_topics, mock_df)

    # Executa a função pura (o Worker)
    resultado = run_suggestion_engine(texts_to_analize=textos_analise, engine_name="motor_fake")  # type: ignore

    # Valida usando a notação de objetos (Pydantic Models)
    assert resultado.total_suggestions == 2
    assert resultado.categories[0].topic_id == 0
    assert resultado.categories[0].suggested_name == "Urbano - Rua - Obras"
    assert resultado.categories[0].estimate_count == 10
    assert len(resultado.categories[0].real_samples) == 10


def test_worker_ignores_noise_topic(mock_registry, mocker):
    """Garante que o tópico '-1' (ruído do BERTopic) é sumariamente ignorado."""
    textos_analise = [f"texto_{i}" for i in range(12)]

    mock_df = pd.DataFrame(
        [
            {"Topic": -1, "Count": 4, "Representation": ["lixo", "ruido", "aleatorio"]},
            {"Topic": 0, "Count": 8, "Representation": ["bom", "certo", "ok"]},
        ]
    )
    mock_topics = [-1] * 4 + [0] * 8

    MockClass = mock_registry(registry)
    instancia_da_ia = MockClass.return_value
    instancia_da_ia.discover_topics.return_value = (mock_topics, mock_df)

    resultado = run_suggestion_engine(texts_to_analize=textos_analise, engine_name="motor_fake")  # type: ignore

    # Apenas o tópico válido (0) deve estar na lista final
    assert resultado.total_suggestions == 1
    assert resultado.categories[0].topic_id == 0


def test_worker_empty_text_list():
    """Garante que o worker aborta caso a lista chegue vazia, protegendo a IA."""
    with pytest.raises(InvalidParam, match="O parâmetro 'texts_to_analize' não foi passado"):
        run_suggestion_engine(texts_to_analize=[], engine_name="motor_fake")  # type: ignore
