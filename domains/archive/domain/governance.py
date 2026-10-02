"""
Write-governance rules for the Archive layer.

Single source of truth for which review statuses freeze a document against any
AI write. The SQL predicate used by workers and repositories is derived from
``AI_LOCKED_REVIEW_STATUSES`` (see
``domains.archive.repository.governance.ai_writable_documents``), so the
``HUMAN_APPROVED`` shield cannot drift between queries.
"""

from domains.archive.models.enums import ArchiveReviewStatus

#: Review statuses whose documents must never be rewritten by an AI worker.
AI_LOCKED_REVIEW_STATUSES: frozenset[ArchiveReviewStatus] = frozenset({ArchiveReviewStatus.HUMAN_APPROVED})
