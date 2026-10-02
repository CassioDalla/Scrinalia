from typing import Any, Literal

from memoria_curitibana.domains.archive.engines.base import TopicDiscoveryEngine
from memoria_curitibana.domains.archive.engines.clustering.bertopic_engine import BERTopicEngine
from memoria_curitibana.domains.archive.engines.clustering.stopwords import STOPWORDS_BR

EngineName = Literal["bertopic"]
PresetName = Literal["exploratory_fine", "exploratory_macro"]


AVAILABLE_ENGINES: dict[EngineName, type[TopicDiscoveryEngine]] = {
    "bertopic": BERTopicEngine,
}

PRESETS: dict[PresetName, dict[str, Any]] = {
    "exploratory_fine": {
        "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
        "min_topic_size": 3,
        "n_gram_range": (1, 2),  # Allows the AI to generate compound keywords
        "nr_topics": "auto",  # Lets the AI discover how many topics naturally exist
        "use_spacy_lemmatizer": True,
    },
    "exploratory_macro": {
        "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
        "min_topic_size": 15,  # Requires more documents to form a cluster (more generic drawers)
        "n_gram_range": (1, 1),
        "nr_topics": "auto",
        "use_spacy_lemmatizer": True,
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

    if engine_name == "bertopic" and final_kwargs.pop("use_spacy_lemmatizer", False):  # noqa: SIM102
        if "analyzer" not in final_kwargs:
            # Imported here rather than at module level: the NER registry pulls in the
            # whole spaCy stack (and torch behind it), which would otherwise be paid by
            # anyone consulting this registry, even when the lemmatizer is not used.
            from memoria_curitibana.domains.archive.engines.NER import registry as ner_registry

            spacy_engine = ner_registry.get_engine("spacy_ner", preset="lemmatizer")

            # Scikit-Learn will call this function passing only the text.
            # We fill in the missing 'stopwords' argument and forward it to its engine!
            def analyzer_wrapper(text: str) -> list[str]:
                return spacy_engine.lemmatize(text, stopwords=STOPWORDS_BR)

            final_kwargs["analyzer"] = analyzer_wrapper

    return AVAILABLE_ENGINES[engine_name](**final_kwargs)
