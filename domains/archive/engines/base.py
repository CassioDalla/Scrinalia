from typing import Protocol

from pandas import DataFrame

from domains.archive.schemas import ArchiveEntityDTO


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


class TopicDiscoveryEngine(Protocol):
    """Contrato usado pelos motores de clustering para"
    descobrir tópicos no arcervo"""

    def discover_topics(self, texts: list[str]) -> tuple[list[int], DataFrame]: ...
