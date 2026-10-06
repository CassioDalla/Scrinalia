from typing import Any, Literal

from memoria_curitibana.domains.archive.engines.base import EmbeddingEngine, describe_engine_config

from .sentence_transformer_engine import SentenceTransformerEngine

EngineName = Literal["sentence_transformer"]
AVAILABLE_ENGINES: dict[EngineName, type[EmbeddingEngine]] = {
    "sentence_transformer": SentenceTransformerEngine,
}

PresetName = Literal["multilingual_minilm"]
# The dimension is fixed by the model: it must match ``EMBEDDING_DIMENSIONS`` in the
# document model (a unit test guards the pair). Changing it means a new column
# dimension and re-embedding the whole collection.
PRESETS: dict[PresetName, dict[str, Any]] = {
    "multilingual_minilm": {
        "model": "paraphrase-multilingual-MiniLM-L12-v2",
        "device": "cpu",
        "batch_size": 32,
        "dimensions": 384,
    },
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs) -> EmbeddingEngine:
    """
    Embedding engine factory.

    Args:
        engine_name: Name of the engine registered in AVAILABLE_ENGINES.
        preset: Name of a base configuration mapped in PRESETS.
        **kwargs: Manual configurations. They override the preset on conflict.
    """
    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    final_kwargs: dict[str, Any] = {}

    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")
        final_kwargs.update(PRESETS[preset])

    final_kwargs.update(kwargs)

    return AVAILABLE_ENGINES[engine_name](**final_kwargs)


def describe_config(engine_name: EngineName, preset: PresetName | None = None, **overrides: Any) -> dict[str, Any]:
    """Effective configuration of the requested engine, without importing torch."""
    return describe_engine_config(AVAILABLE_ENGINES, PRESETS, engine_name, preset, **overrides)
