from typing import TYPE_CHECKING, Any

from pandas import DataFrame
from sklearn.feature_extraction.text import CountVectorizer

from scrinalia.domains.archive.engines.clustering.stopwords import STOPWORDS_BR

if TYPE_CHECKING:
    pass


class BERTopicEngine:
    """
    Topic discovery engine backed by BERTopic.

    ``bertopic`` is imported inside ``__init__`` on purpose: the package takes about
    ten seconds to import and drags in umap, pynndescent and sentence-transformers.
    Importing it at module level made every consumer of this registry pay that cost,
    including the API, which reaches this engine through a single optional route.
    """

    def __init__(self, embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2", **kwargs: Any) -> None:
        from bertopic import BERTopic

        analyzer = kwargs.pop("analyzer", "word")
        vectorizer_model = CountVectorizer(analyzer=analyzer, stop_words=STOPWORDS_BR)

        config: dict[str, Any] = {
            "language": "multilingual",
            "calculate_probabilities": False,
            "verbose": False,
            "vectorizer_model": vectorizer_model,
        }

        config.update(kwargs)

        self.model: BERTopic = BERTopic(embedding_model=embedding_model, **config)

    def discover_topics(self, texts: list[str]) -> tuple[list[int], DataFrame]:
        topics, _ = self.model.fit_transform(texts)
        topic_info = self.model.get_topic_info()

        return topics, topic_info
