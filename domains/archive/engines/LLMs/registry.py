from typing import Any, Literal

from domains.archive.engines.base import ResolveTagEntityConflictEngine
from domains.archive.engines.LLMs.ollama_tag_entity_conflict import OllamaJudgeEngine

EngineName = Literal["ollama_judge"]
AVAILABLE_ENGINES: dict[EngineName, type[ResolveTagEntityConflictEngine]] = {
    "ollama_judge": OllamaJudgeEngine,
}

PresetName = Literal["granite_local", "gemma_4b_local"]
PRESETS: dict[PresetName, dict[str, Any]] = {
    "granite_local": {"model": "granite4.1:3b", "host": "http://localhost:11434"},
    "gemma_4b_local": {"model": "gemma4:e4b", "host": "http://localhost:11434"},
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs) -> ResolveTagEntityConflictEngine:
    """
    Fábrica de motores de julgamento de conflitos de IA.

    Args:
        engine_name: Nome do motor registrado em AVAILABLE_ENGINES.
        preset: Nome de uma configuração base mapeada em PRESETS.
        **kwargs: Configurações manuais. Sobrescrevem o preset se houver conflito.
    """
    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    final_kwargs = {}

    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")

        final_kwargs.update(dict(PRESETS[preset]))

    final_kwargs.update(kwargs)

    return AVAILABLE_ENGINES[engine_name](**final_kwargs)
