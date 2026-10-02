from bertopic import BERTopic
from pandas import DataFrame
from sklearn.feature_extraction.text import CountVectorizer

from memoria_curitibana.domains.archive.engines.clustering.stopwords import STOPWORDS_BR


class BERTopicEngine:
    def __init__(self, embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2", **kwargs):
        analyzer = kwargs.pop("analyzer", "word")
        vectorizer_model = CountVectorizer(analyzer=analyzer, stop_words=STOPWORDS_BR)

        config = {
            "language": "multilingual",
            "calculate_probabilities": False,
            "verbose": False,
            "vectorizer_model": vectorizer_model,
        }

        config.update(kwargs)

        self.model = BERTopic(embedding_model=embedding_model, **config)

    def discover_topics(self, texts: list[str]) -> tuple[list[int], DataFrame]:
        topics, _ = self.model.fit_transform(texts)
        topic_info = self.model.get_topic_info()

        return topics, topic_info
