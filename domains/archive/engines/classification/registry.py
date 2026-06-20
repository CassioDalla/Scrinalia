from typing import Any, Literal

from ..base import TypologyEngine
from .deberta_typology import DebertaEngine
from .ollama_typology import OllamaTypologyEngine

EngineName = Literal["deberta_typology", "ollama_typology"]
AVAILABLE_ENGINES: dict[EngineName, type[TypologyEngine]] = {
    "deberta_typology": DebertaEngine,
    "ollama_typology": OllamaTypologyEngine,  # type: ignore
}

PresetName = Literal["cpu_local", "gpu_cloud"]
PRESETS: dict[PresetName, dict[str, Any]] = {
    "cpu_local": {"model": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", "device": "cpu"},
    "gpu_cloud": {"model": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", "device": "cuda"},
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs) -> TypologyEngine:
    """
    Fábrica de motores de tipologia.

    Args:
        engine_name: Nome do motor registrado em AVAILABLE_ENGINES.
        preset: Nome de uma configuração base mapeada em PRESETS.
        **kwargs: Configurações manuais. Sobrescrevem o preset se houver conflito.
    """
    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    final_kwargs = {}

    # 1. Se o utilizador pediu um preset, carregamos a base de configuração dele primeiro
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")

        final_kwargs.update(PRESETS[preset])

    # 2. O utilizador tem SEMPRE a última palavra.
    # O que vier no **kwargs manual sobrescreve as chaves do preset se tiverem o mesmo nome.
    final_kwargs.update(kwargs)

    # 3. Instancia o motor desempacotando o dicionário final combinado
    return AVAILABLE_ENGINES[engine_name](**final_kwargs)
