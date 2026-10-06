from collections.abc import Mapping
from typing import Any, Protocol

from pandas import DataFrame

from memoria_curitibana.domains.archive.schemas import (
    ArchiveEntityDTO,
    EntityTagDecisionSchema,
    TitleQualityDecision,
)


def describe_engine_config(
    available_engines: Mapping[Any, Any],
    presets: Mapping[Any, Mapping[str, Any]],
    engine_name: str,
    preset: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """
    Resolves the effective engine configuration **without instantiating the engine**.

    The operational panel has to answer "with which preset and which model is this worker
    going to run?" for a worker that may not have run yet, so it cannot pay the cost of
    loading spaCy, torch or BERTopic just to read a preset. This function is the read-only
    twin of ``get_engine``: it applies the exact same precedence (preset first, manual
    overrides on top) and validates the same names, but returns the merged dictionary.

    ``get_engine`` deliberately keeps its own implementation: it is the hot path of every
    worker and the two registries that inject an environment host would otherwise have to be
    restructured. A test pins the two together by capturing the kwargs ``get_engine``
    forwards and comparing them with what this function describes.
    """
    if engine_name not in available_engines:
        raise ValueError(f"Motor '{engine_name}' não suportado. Opções: {list(available_engines.keys())}")

    final_kwargs: dict[str, Any] = {}

    if preset:
        if preset not in presets:
            raise ValueError(f"Preset '{preset}' não encontrado. Opções: {list(presets.keys())}")
        final_kwargs.update(presets[preset])

    final_kwargs.update(overrides)
    return final_kwargs


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


class TitleQualityEngine(Protocol):
    """
    Contract for the optional language-model opinion about a title.

    It exists so the anomaly validator can call an LLM without owning one: the archivist
    has to register an active ``LLM_CHECK`` rule, and only then is an engine built.
    """

    def check_title(self, title: str) -> TitleQualityDecision: ...
