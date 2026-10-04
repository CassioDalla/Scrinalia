from typing import Protocol

from pandas import DataFrame

from memoria_curitibana.domains.archive.schemas import ArchiveEntityDTO, EntityTagDecisionSchema


class TypologyEngine(Protocol):
    """
    Contract that every archive classification engine must follow.
    """

    def classify(self, texts: list[str], candidate_labels: list[str], **kwargs) -> list[dict]: ...


class EntityExtractionEngine(Protocol):
    """
    Contract that every archive classification engine must follow.
    """

    def extract(
        self,
        texts: list[str],
    ) -> list[list[ArchiveEntityDTO]]:
        """
        Receives a list of texts and returns a list of results.
        Each result is a list of Entities found in that respective text.
        """
        ...

    def lemmatize(self, text: str, stopwords: list[str]) -> list[str]: ...


class TopicDiscoveryEngine(Protocol):
    """Contract used by clustering engines to
    discover topics in the archive."""

    def discover_topics(self, texts: list[str]) -> tuple[list[int], DataFrame]: ...


class EmbeddingEngine(Protocol):
    """
    Contract used by the semantic-search engines to turn text into vectors.

    The vectors are stored on the document and compared with cosine distance, so the
    engine owns both the model and its dimension; the column dimension and the preset
    are guarded by a test.
    """

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ResolveTagEntityConflictEngine(Protocol):
    """
    Contract used by AI engines (LLMs) that decide semantic ties
    between two taxonomies (e.g. Tag vs Entity).
    """

    def decide_conflict(self, tag_name: str, entity_name: str, entity_type: str) -> EntityTagDecisionSchema: ...
