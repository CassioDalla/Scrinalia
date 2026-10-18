from typing import Any, Literal

from scrinalia.core.config import resolve_ollama_host
from scrinalia.domains.archive.engines.base import (
    ResolveTagEntityConflictEngine,
    describe_engine_config,
    refuse_retired_preset,
)
from scrinalia.domains.archive.engines.LLMs.ollama_tag_entity_conflict import OllamaJudgeEngine

EngineName = Literal["ollama_judge"]
AVAILABLE_ENGINES: dict[EngineName, type[ResolveTagEntityConflictEngine]] = {
    "ollama_judge": OllamaJudgeEngine,
}

PresetName = Literal["gemma_4b_local"]
#: The host is not part of a preset: it comes from ``OLLAMA_HOST_URL`` (``resolve_ollama_host``).
PRESETS: dict[PresetName, dict[str, Any]] = {
    "gemma_4b_local": {"model": "gemma4:e4b"},
}

#: Presets that were declared and no longer run, mapped to the reason. Measured on 2026-10-18, on
#: Ollama 0.24.0: ``granite4.1:3b`` terminates the llama runner with "signal arrived during cgo
#: execution" and answers 500 to every prompt, while ``gemma4:e4b`` answers normally on the same
#: server. A preset is removed from ``PRESETS`` — so the panel stops offering it and
#: ``GET /system/health`` stops requiring the model — but the record that it existed stays here
#: (principle VI), and ``refuse_retired_preset`` answers an operator who still names it with the
#: reason instead of "não encontrado".
RETIRED_PRESETS: dict[str, str] = {
    "granite_local": (
        "granite4.1:3b derruba o llama runner no Ollama 0.24.0 ('signal arrived during cgo execution') "
        "e responde 500 a todo prompt; use gemma_4b_local."
    ),
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

    refuse_retired_preset(preset, RETIRED_PRESETS)

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
    refuse_retired_preset(preset, RETIRED_PRESETS)
    config = describe_engine_config(AVAILABLE_ENGINES, PRESETS, engine_name, preset, **overrides)
    config["host"] = resolve_ollama_host(config.get("host"))
    return config
