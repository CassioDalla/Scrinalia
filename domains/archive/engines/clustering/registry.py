from typing import Any, Literal

from domains.archive.engines.base import TopicDiscoveryEngine
from domains.archive.engines.clustering.bertopic_engine import BERTopicEngine

EngineName = Literal["bertopic"]
PresetName = Literal["exploratorio_fino", "exploratorio_macro"]


AVAILABLE_ENGINES: dict[EngineName, type[TopicDiscoveryEngine]] = {
    "bertopic": BERTopicEngine,
}

PRESETS: dict[PresetName, dict[str, Any]] = {
    "exploratorio_fino": {
        "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
        "min_topic_size": 3,
        "n_gram_range": (1, 2),  # Permite que a IA gere palavras-chave compostas
        "nr_topics": "auto",  # Deixa a IA descobrir quantos tópicos existem naturalmente
    },
    "exploratorio_macro": {
        "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
        "min_topic_size": 15,  # Exige mais documentos para formar um cluster (gavetas mais genéricas)
        "n_gram_range": (1, 1),
        "nr_topics": 10,  # Força a redução para no máximo 10 grandes áreas temáticas
    },
}


def get_engine(engine_name: EngineName, preset: PresetName | None = None, **kwargs) -> TopicDiscoveryEngine:

    if engine_name not in AVAILABLE_ENGINES:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(AVAILABLE_ENGINES.keys())}")

    final_kwargs = {}

    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(PRESETS.keys())}")
        final_kwargs.update(PRESETS[preset])

    final_kwargs.update(kwargs)

    return AVAILABLE_ENGINES[engine_name](**final_kwargs)
