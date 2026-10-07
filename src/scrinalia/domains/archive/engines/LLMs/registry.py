from typing import Any, Literal

from scrinalia.core.config import resolve_ollama_host
from scrinalia.domains.archive.engines.base import ResolveTagEntityConflictEngine, describe_engine_config
from scrinalia.domains.archive.engines.LLMs.ollama_tag_entity_conflict import OllamaJudgeEngine

EngineName = Literal["ollama_judge"]
AVAILABLE_ENGINES: dict[EngineName, type[ResolveTagEntityConflictEngine]] = {
    "ollama_judge": OllamaJudgeEngine,
}

PresetName = Literal["granite_local", "gemma_4b_local"]
#: The host is not part of a preset: it comes from ``OLLAMA_HOST_URL`` (``resolve_ollama_host``).
PRESETS: dict[PresetName, dict[str, Any]] = {
    "granite_local": {"model": "granite4.1:3b"},
    "gemma_4b_local": {"model": "gemma4:e4b"},
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs) -> ResolveTagEntityConflictEngine:
    """
    AI conflict-judging engine factory.

    Args:
        engine_name: Name of the engine registered in AVAILABLE_ENGINES.
        preset: Name of a base configuration mapped in PRESETS.
        **kwargs: Manual configurations. They override the preset on conflict.
    """
    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    final_kwargs = {}

    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")

        final_kwargs.update(dict(PRESETS[preset]))

    final_kwargs.update(kwargs)

    # The environment only fills the host when the caller did not name one; an explicit
    # ``--option host=...`` still wins, which is what makes a per-run override possible.
    final_kwargs["host"] = resolve_ollama_host(final_kwargs.get("host"))

    return AVAILABLE_ENGINES[engine_name](**final_kwargs)


def describe_config(engine_name: EngineName, preset: PresetName | None = None, **overrides: Any) -> dict[str, Any]:
    """Effective configuration of the requested engine, including the host it will call."""
    config = describe_engine_config(AVAILABLE_ENGINES, PRESETS, engine_name, preset, **overrides)
    config["host"] = resolve_ollama_host(config.get("host"))
    return config
