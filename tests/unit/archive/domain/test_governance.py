from domains.archive.domain.governance import AI_LOCKED_REVIEW_STATUSES, DocumentWritePolicy
from domains.archive.models.enums import ArchiveReviewStatus
from domains.archive.repository.governance import ai_writable_documents


def test_human_approved_is_the_only_locked_status() -> None:
    assert frozenset({ArchiveReviewStatus.HUMAN_APPROVED}) == AI_LOCKED_REVIEW_STATUSES


def test_can_ai_write_only_blocks_human_approved() -> None:
    assert DocumentWritePolicy.can_ai_write(ArchiveReviewStatus.PENDING_AI) is True
    assert DocumentWritePolicy.can_ai_write(ArchiveReviewStatus.AI_APPROVED) is True
    assert DocumentWritePolicy.can_ai_write(ArchiveReviewStatus.NEEDS_REVIEW) is True
    assert DocumentWritePolicy.can_ai_write(ArchiveReviewStatus.HUMAN_APPROVED) is False


def test_ai_writable_documents_excludes_locked_statuses() -> None:
    compiled = str(ai_writable_documents().compile(compile_kwargs={"literal_binds": True}))

    assert "archive_documents.review_status" in compiled
    assert "HUMAN_APPROVED" in compiled
    assert "NOT IN" in compiled
