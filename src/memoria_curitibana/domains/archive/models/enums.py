import enum


class ArchiveReviewStatus(enum.StrEnum):
    """
    Controls the lifecycle of human validation
    over the AI's work.
    """

    PENDING_AI = "PENDING_AI"  # Waiting for the AI pipelines to run
    AI_APPROVED = "AI_APPROVED"  # The AI corrected/classified with high confidence
    NEEDS_REVIEW = "NEEDS_REVIEW"  # The AI found an anomaly or had low confidence
    HUMAN_APPROVED = "HUMAN_APPROVED"  # The human validated or corrected manually (Blocks AI Editing)
    REJECTED = "REJECTED"  # The human decided the data is garbage


class StopwordsScope(enum.StrEnum):
    """
    Controls the scope of a domain stopword
    """

    TAG = "TAG"  # Applied as a stopword only to tags
    ENTITY = "ENTITY"
    ALL = "ALL"


class AnomalyType(enum.StrEnum):
    CROSS_DOMAIN_COLLISION = "CROSS_DOMAIN_COLLISION"
