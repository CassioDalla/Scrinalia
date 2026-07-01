import enum


class ArchiveReviewStatus(enum.StrEnum):
    """
    Controla o ciclo de vida da validação humana
    sobre o trabalho da IA.
    """

    PENDING_AI = "PENDING_AI"  # Aguardando os pipelines de IA rodarem
    AI_APPROVED = "AI_APPROVED"  # A IA corrigiu/classificou com alta confiança
    NEEDS_REVIEW = "NEEDS_REVIEW"  # A IA achou anomalia ou teve baixa confiança
    HUMAN_APPROVED = "HUMAN_APPROVED"  # O humano validou ou corrigiu manualmente (Trava Edição de IA)
    REJECTED = "REJECTED"  # O humano definiu que o dado é lixo


class StopwordsScope(enum.StrEnum):
    """
    Controla o escopo de uma stopword de dominio
    """

    TAG = "TAG"  # Aplicada a stowords apenas a tags
    ENTITY = "ENTITY"
    ALL = "ALL"


class AnomalyType(enum.StrEnum):
    CROSS_DOMAIN_COLLISION = "CROSS_DOMAIN_COLLISION"
