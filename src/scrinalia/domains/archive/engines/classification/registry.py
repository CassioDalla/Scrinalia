from typing import Any, Literal

from ..base import TypologyEngine, describe_engine_config
from .deberta_typology import DebertaEngine
from .ollama_typology import OllamaTypologyEngine

EngineName = Literal["deberta_typology", "ollama_typology"]
AVAILABLE_ENGINES: dict[EngineName, type[TypologyEngine]] = {
    "deberta_typology": DebertaEngine,
    "ollama_typology": OllamaTypologyEngine,  # type: ignore
}

PresetName = Literal["cpu_local", "gpu_cloud", "xlm_roberta_local"]
PRESETS: dict[PresetName, dict[str, Any]] = {
    "cpu_local": {"model": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", "device": "cpu"},
    "gpu_cloud": {"model": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", "device": "cuda"},
    # The second model the axis can run. It exists because the subject bench (`macro_category_quality`)
    # compares two models on the same golden set, and the bench names no model: it asks the registry
    # for a configuration, exactly as both workers of this axis do. ``DebertaEngine`` is a
    # ``zero-shot-classification`` pipeline whose model is a parameter, so a model is a preset here
    # and not an engine — and the consequence is deliberate: the option reaches the typology worker's
    # panel too, because this registry is the axis's single definition of what can be run.
    "xlm_roberta_local": {"model": "joeddav/xlm-roberta-large-xnli", "device": "cpu"},
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs) -> TypologyEngine:
    """
    Typology engine factory.

    Args:
        engine_name: Name of the engine registered in AVAILABLE_ENGINES.
        preset: Name of a base configuration mapped in PRESETS.
        **kwargs: Manual configurations. They override the preset on conflict.
    """
    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    final_kwargs = {}

    # 1. If the user requested a preset, we load its base configuration first
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")

        final_kwargs.update(PRESETS[preset])

    # 2. The user ALWAYS has the final say.
    # Whatever comes in the manual **kwargs overrides preset keys with the same name.
    final_kwargs.update(kwargs)

    # 3. Instantiates the engine by unpacking the final combined dictionary
    return AVAILABLE_ENGINES[engine_name](**final_kwargs)


def describe_config(engine_name: EngineName, preset: PresetName | None = None, **overrides: Any) -> dict[str, Any]:
    """Effective configuration of the requested engine, without importing transformers."""
    return describe_engine_config(AVAILABLE_ENGINES, PRESETS, engine_name, preset, **overrides)
