"""SQL fragment that renders the AI write-governance rule from the domain."""

from sqlalchemy import ColumnElement

from domains.archive.domain.governance import AI_LOCKED_REVIEW_STATUSES
from domains.archive.models import ArchiveDocument


def ai_writable_documents() -> ColumnElement[bool]:
    """Predicate selecting the documents an AI worker is still allowed to mutate."""
    return ArchiveDocument.review_status.notin_(AI_LOCKED_REVIEW_STATUSES)
