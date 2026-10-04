from typing import Any, Literal

from memoria_curitibana.domains.archive.engines.base import TitleQualityEngine
from memoria_curitibana.domains.archive.engines.title_quality.ollama_title_check import OllamaTitleCheckEngine

#: Registered title reviewers. Empty by design would be a lie: the LLM stage is optional
#: but the engine it needs has to exist for an ``LLM_CHECK`` rule to mean anything.
EngineName = Literal["ollama_title_check"]
AVAILABLE_ENGINES: dict[EngineName, type[TitleQualityEngine]] = {
    "ollama_title_check": OllamaTitleCheckEngine,
}

PresetName = Literal["granite_local", "gemma_4b_local"]
PRESETS: dict[PresetName, dict[str, Any]] = {
    "granite_local": {"model": "granite4.1:3b", "host": "http://localhost:11434"},
    "gemma_4b_local": {"model": "gemma4:e4b", "host": "http://localhost:11434"},
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs) -> TitleQualityEngine:
    """Builds the requested title reviewer, preset first and manual kwargs on top."""
    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    final_kwargs: dict[str, Any] = {}
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")
        final_kwargs.update(dict(PRESETS[preset]))

    final_kwargs.update(kwargs)
    return AVAILABLE_ENGINES[engine_name](**final_kwargs)
