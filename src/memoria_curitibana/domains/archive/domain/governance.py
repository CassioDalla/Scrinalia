"""
Write-governance rules for the Archive layer.

Single source of truth for which review statuses freeze a document against any
AI write. Both the SQL predicate used by workers and repositories
(``domains.archive.repository.governance.ai_writable_documents``) and the
pre-write guards read from ``DocumentWritePolicy``, so the ``HUMAN_APPROVED``
shield cannot drift between queries.
"""

from memoria_curitibana.domains.archive.models.enums import ArchiveReviewStatus


class DocumentWritePolicy:
    """Specification of the review statuses that allow an AI write."""

    LOCKED_STATUSES: frozenset[ArchiveReviewStatus] = frozenset({ArchiveReviewStatus.HUMAN_APPROVED})

    @classmethod
    def can_ai_write(cls, review_status: ArchiveReviewStatus) -> bool:
        """True when an AI worker may still mutate a document in this state."""
        return review_status not in cls.LOCKED_STATUSES


#: Review statuses whose documents must never be rewritten by an AI worker.
AI_LOCKED_REVIEW_STATUSES = DocumentWritePolicy.LOCKED_STATUSES
