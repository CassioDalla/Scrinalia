from bertopic import BERTopic
from pandas import DataFrame


class BERTopicEngine:
    def __init__(
        self, language="multilingual", embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2", **kwargs
    ):
        self.model = BERTopic(language=language, embedding_model=embedding_model, **kwargs)

    def discover_topics(self, texts: list[str]) -> tuple[list[int], DataFrame]:
        topics, _ = self.model.fit_transform(texts)
        topic_info = self.model.get_topic_info()

        return topics, topic_info
