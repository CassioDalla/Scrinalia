from typing import Protocol


class TypologyEngine(Protocol):
    """
    Contrato que todo motor de classificação do acervo deve seguir.
    """

    def classify(self, texts: list[str], candidate_labels: list[str], **kwargs) -> list[dict]: ...


## Fazer outras classes para outros tipos de motores
