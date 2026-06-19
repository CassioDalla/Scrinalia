from typing import Protocol

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
