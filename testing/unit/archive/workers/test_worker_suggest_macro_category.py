import pandas as pd
import pytest

from memoria_curitibana.domains.archive.engines.clustering import registry
from memoria_curitibana.domains.archive.exceptions import EngineExecutionError, InvalidParam
from memoria_curitibana.domains.archive.workers.worker_suggest_macro_category import (
    resolve_min_topic_size,
    run_suggestion_engine,
)


def _topic_info() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Topic": 0, "Count": 10, "Representation": ["urbano", "rua", "obras"]},
            {"Topic": 1, "Count": 5, "Representation": ["lei", "decreto", "oficio"]},
        ]
    )


def test_worker_happy_path_formatting(mock_registry, mocker):
    """Guarantees that the worker formats the BERTopic DataFrame into the Pydantic DTO."""
    analysis_texts = [f"texto_{i}" for i in range(15)]

    mock_topics = [0] * 10 + [1] * 5

    MockClass = mock_registry(registry)
    ai_instance = MockClass.return_value
    ai_instance.discover_topics.return_value = (mock_topics, _topic_info())

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


# ==========================================
# ADAPTIVE min_topic_size
# ==========================================


def test_resolve_min_topic_size_scales_with_corpus() -> None:
    """The fixed preset ceiling is relaxed for a real, small collection."""
    # The verified real case: 39 tags broke with the preset's 15 and worked with 3.
    assert resolve_min_topic_size("exploratory_macro", 39) == 3
    assert resolve_min_topic_size("exploratory_macro", 500) == 15
    assert resolve_min_topic_size("exploratory_macro", 12) == 2
    # Never below 2: a one-text cluster is noise.
    assert resolve_min_topic_size("exploratory_fine", 5) == 2


def test_worker_passes_adaptive_size_to_the_engine(mock_registry) -> None:
    """The preset's fixed min_topic_size must not reach the engine unadapted."""
    analysis_texts = [f"texto_{i}" for i in range(39)]

    MockClass = mock_registry(registry)
    MockClass.return_value.discover_topics.return_value = ([0] * 39, _topic_info())

    run_suggestion_engine(texts_to_analyze=analysis_texts, engine_name="motor_fake")  # type: ignore

    _, kwargs = MockClass.call_args
    assert kwargs["min_topic_size"] == 3


# ==========================================
# FALLBACK AND DEGRADED VOLUME
# ==========================================


def test_worker_falls_back_to_fine_preset(mock_registry) -> None:
    """When the macro preset cannot cluster, the routine retries once with the fine preset."""
    analysis_texts = [f"texto_{i}" for i in range(20)]

    mock_topics = [0] * 10 + [1] * 10

    MockClass = mock_registry(registry)
    ai_instance = MockClass.return_value
    ai_instance.discover_topics.side_effect = [
        Exception("Found array with 0 sample(s) (shape=(0, 384))"),
        (mock_topics, _topic_info()),
    ]

    result = run_suggestion_engine(texts_to_analyze=analysis_texts, engine_name="motor_fake")  # type: ignore

    assert ai_instance.discover_topics.call_count == 2
    assert result.total_suggestions == 2


def test_worker_returns_empty_response_when_nothing_clusters(mock_registry) -> None:
    """Insufficient data is an empty suggestion with a message, never a 422."""
    analysis_texts = [f"texto_{i}" for i in range(20)]

    MockClass = mock_registry(registry)
    ai_instance = MockClass.return_value
    ai_instance.discover_topics.side_effect = Exception("Found array with 0 sample(s)")

    result = run_suggestion_engine(texts_to_analyze=analysis_texts, engine_name="motor_fake")  # type: ignore

    assert result.total_suggestions == 0
    assert result.categories == []
    assert result.message is not None


def test_worker_raises_on_unknown_engine(mock_registry) -> None:
    """A configuration mistake is surfaced, not disguised as 'not enough data'."""
    with pytest.raises(EngineExecutionError):
        run_suggestion_engine(texts_to_analyze=["a"] * 20, engine_name="motor_inexistente")  # type: ignore
