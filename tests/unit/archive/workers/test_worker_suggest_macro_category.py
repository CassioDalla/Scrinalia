import pandas as pd
import pytest

from domains.archive.engines.clustering import registry
from domains.archive.exceptions import InvalidParam
from domains.archive.workers.worker_suggest_macro_category import run_suggestion_engine


def test_worker_happy_path_formatting(mock_registry, mocker):
    """Guarantees that the worker formats the BERTopic DataFrame into the Pydantic DTO."""
    analysis_texts = [f"texto_{i}" for i in range(15)]

    # Simulates the BERTopic output
    mock_df = pd.DataFrame(
        [
            {"Topic": 0, "Count": 10, "Representation": ["urbano", "rua", "obras"]},
            {"Topic": 1, "Count": 5, "Representation": ["lei", "decreto", "oficio"]},
        ]
    )
    mock_topics = [0] * 10 + [1] * 5

    MockClass = mock_registry(registry)
    ai_instance = MockClass.return_value
    ai_instance.discover_topics.return_value = (mock_topics, mock_df)

    # Run the pure function (the Worker)
    result = run_suggestion_engine(texts_to_analyze=analysis_texts, engine_name="motor_fake")  # type: ignore

    # Validate using object notation (Pydantic Models)
    assert result.total_suggestions == 2
    assert result.categories[0].topic_id == 0
    assert result.categories[0].suggested_name == "Urbano - Rua - Obras"
    assert result.categories[0].estimate_count == 10
    assert len(result.categories[0].real_samples) == 10


def test_worker_ignores_noise_topic(mock_registry, mocker):
    """Guarantees that topic '-1' (BERTopic noise) is summarily ignored."""
    analysis_texts = [f"texto_{i}" for i in range(12)]

    mock_df = pd.DataFrame(
        [
            {"Topic": -1, "Count": 4, "Representation": ["lixo", "ruido", "aleatorio"]},
            {"Topic": 0, "Count": 8, "Representation": ["bom", "certo", "ok"]},
        ]
    )
    mock_topics = [-1] * 4 + [0] * 8

    MockClass = mock_registry(registry)
    ai_instance = MockClass.return_value
    ai_instance.discover_topics.return_value = (mock_topics, mock_df)

    result = run_suggestion_engine(texts_to_analyze=analysis_texts, engine_name="motor_fake")  # type: ignore

    # Only the valid topic (0) must be in the final list
    assert result.total_suggestions == 1
    assert result.categories[0].topic_id == 0


def test_worker_empty_text_list():
    """Guarantees that the worker aborts if the list arrives empty, protecting the AI."""
    with pytest.raises(InvalidParam, match="O parâmetro 'texts_to_analyze' não foi passado"):
        run_suggestion_engine(texts_to_analyze=[], engine_name="motor_fake")  # type: ignore
