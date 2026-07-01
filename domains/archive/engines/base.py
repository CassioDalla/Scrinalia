from typing import Protocol

from pandas import DataFrame

from domains.archive.schemas import ArchiveEntityDTO, EntityTagDecisionSchema


class TypologyEngine(Protocol):
    """
    Contrato que todo motor de classificação do acervo deve seguir.
    """

    def classify(self, texts: list[str], candidate_labels: list[str], **kwargs) -> list[dict]: ...


class EntityExtractionEngine(Protocol):
    """
    Contrato que todo motor de classificação do acervo deve seguir.
    """

    def extract(
        self,
        texts: list[str],
    ) -> list[list[ArchiveEntityDTO]]:
        """
        Recebe uma lista de textos e retorna uma lista de resultados.
        Cada resultado é uma lista de Entidades encontradas naquele respectivo texto.
        """
        ...

    def lemmatize(self, text: str, stopwords: list[str]) -> list[str]: ...


class TopicDiscoveryEngine(Protocol):
    """Contrato usado pelos motores de clustering para"
    descobrir tópicos no arcervo"""

    def discover_topics(self, texts: list[str]) -> tuple[list[int], DataFrame]: ...


class ResolveTagEntityConflictEngine(Protocol):
    """
    Contrato usado por motores de IA (LLMs) que decidem empates semânticos
    entre duas taxonomias (ex: Tag vs Entidade).
    """

    def decide_conflict(self, tag_name: str, entity_name: str, entity_type: str) -> EntityTagDecisionSchema: ...
