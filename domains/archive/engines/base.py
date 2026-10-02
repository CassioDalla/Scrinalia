from typing import Protocol

from pandas import DataFrame

from domains.archive.schemas import ArchiveEntityDTO, EntityTagDecisionSchema


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


class ResolveTagEntityConflictEngine(Protocol):
    """
    Contract used by AI engines (LLMs) that decide semantic ties
    between two taxonomies (e.g. Tag vs Entity).
    """

    def decide_conflict(self, tag_name: str, entity_name: str, entity_type: str) -> EntityTagDecisionSchema: ...
