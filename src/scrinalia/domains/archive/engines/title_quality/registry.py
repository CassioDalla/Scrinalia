from typing import Any, Literal

from scrinalia.core.config import resolve_ollama_host
from scrinalia.domains.archive.engines.base import (
    TitleQualityEngine,
    describe_engine_config,
    refuse_retired_preset,
)
from scrinalia.domains.archive.engines.title_quality.ollama_title_check import OllamaTitleCheckEngine

#: Registered title reviewers. Empty by design would be a lie: the LLM stage is optional
#: but the engine it needs has to exist for an ``LLM_CHECK`` rule to mean anything.
EngineName = Literal["ollama_title_check"]
AVAILABLE_ENGINES: dict[EngineName, type[TitleQualityEngine]] = {
    "ollama_title_check": OllamaTitleCheckEngine,
}

PresetName = Literal["gemma_4b_local"]
#: The host is not part of a preset: it comes from ``OLLAMA_HOST_URL`` (``resolve_ollama_host``).
PRESETS: dict[PresetName, dict[str, Any]] = {
    "gemma_4b_local": {"model": "gemma4:e4b"},
}

#: The same retirement as the conflict judge's, because it is the same model that does not run: the
#: title reviewer names ``granite4.1:3b`` through this axis, and an operator's ``LLM_CHECK`` rule
#: still pointing at the retired name is answered with the reason instead of "não encontrado".
RETIRED_PRESETS: dict[str, str] = {
    "granite_local": (
        "granite4.1:3b derruba o llama runner no Ollama 0.24.0 ('signal arrived during cgo execution') "
        "e responde 500 a todo prompt; use gemma_4b_local."
    ),
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs) -> TitleQualityEngine:
    """Builds the requested title reviewer, preset first and manual kwargs on top."""
    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    refuse_retired_preset(preset, RETIRED_PRESETS)

    final_kwargs: dict[str, Any] = {}
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")
        final_kwargs.update(dict(PRESETS[preset]))

    final_kwargs.update(kwargs)
    # Explicit host first, then the environment: the same rule as the conflict judge.
    final_kwargs["host"] = resolve_ollama_host(final_kwargs.get("host"))
    return AVAILABLE_ENGINES[engine_name](**final_kwargs)


def describe_config(engine_name: EngineName, preset: PresetName | None = None, **overrides: Any) -> dict[str, Any]:
    """Effective configuration of the requested reviewer, including the host it will call."""
    refuse_retired_preset(preset, RETIRED_PRESETS)
    config = describe_engine_config(AVAILABLE_ENGINES, PRESETS, engine_name, preset, **overrides)
    config["host"] = resolve_ollama_host(config.get("host"))
    return config
