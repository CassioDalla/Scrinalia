from typing import Any, Literal

from domains.archive.engines.base import EntityExtractionEngine

from .spacy_engine import SpacyEngine

EngineName = Literal["spacy_ner"]
PresetName = Literal["gpu", "lemmatizer"]

AVAILABLE_ENGINES: dict[EngineName, type[EntityExtractionEngine]] = {
    "spacy_ner": SpacyEngine,
}

PRESETS: dict[PresetName, dict[str, Any]] = {
    "gpu": {"model": "pt_core_news_lg", "device": "gpu"},
    "lemmatizer": {"model": "pt_core_news_lg", "device": "gpu", "disable": ["ner", "parser"]},
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs: Any) -> EntityExtractionEngine:

    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    final_kwargs = {}

    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")
        final_kwargs.update(PRESETS[preset])

    final_kwargs.update(kwargs)

    return AVAILABLE_ENGINES[engine_name](**final_kwargs)
