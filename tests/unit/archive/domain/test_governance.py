from domains.archive.domain.governance import AI_LOCKED_REVIEW_STATUSES
from domains.archive.models.enums import ArchiveReviewStatus
from domains.archive.repository.governance import ai_writable_documents


def test_human_approved_is_the_only_locked_status() -> None:
    assert frozenset({ArchiveReviewStatus.HUMAN_APPROVED}) == AI_LOCKED_REVIEW_STATUSES


def test_ai_writable_documents_excludes_locked_statuses() -> None:
    compiled = str(ai_writable_documents().compile(compile_kwargs={"literal_binds": True}))

    assert "archive_documents.review_status" in compiled
    assert "HUMAN_APPROVED" in compiled
    assert "NOT IN" in compiled
