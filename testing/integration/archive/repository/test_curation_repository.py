"""The counts behind the curator's work list, against real PostgreSQL."""

from scrinalia.domains.archive.models import (
    ArchiveHierarchyNodePlan,
    ArchiveReviewStatus,
    ArchiveTag,
    ArchiveTagMergeProposal,
)
from scrinalia.domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue
from scrinalia.domains.archive.repository.curation_repo import CurationRepository
from scrinalia.domains.archive.services.curation_service import QUEUE_CATALOGUE


def test_an_empty_collection_reports_every_queue_at_zero(db_session) -> None:
    """
    Zero, not missing.

    The home screen has to be able to say "this queue exists and is empty", which is a different
    statement from "this queue was never built" — and the second is what an absent key would mean.
    """
    counts = CurationRepository(db_session).count_pending()

    assert set(counts) == {key for key, *_ in QUEUE_CATALOGUE}
    assert set(counts.values()) == {0}


def test_unreviewed_documents_counts_only_the_pending_ones(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="c1", original_title="A")
    generate_archive_doc(description_id="c2", original_title="B", review_status=ArchiveReviewStatus.HUMAN_APPROVED)
    generate_archive_doc(description_id="c3", original_title="C", review_status=ArchiveReviewStatus.PENDING_AI)
    db_session.flush()

    assert CurationRepository(db_session).count_unreviewed_documents() == 2


def test_anomalies_counts_the_flagged_documents(db_session, generate_archive_doc) -> None:
    generate_archive_doc(description_id="a1", original_title="A", is_anomaly=True)
    generate_archive_doc(description_id="a2", original_title="B")
    db_session.flush()

    assert CurationRepository(db_session).count_anomalies() == 1


def test_orphan_subject_tags_counts_the_tags_without_a_drawer(db_session) -> None:
    db_session.add_all([ArchiveTag(name="com-gaveta", macro_category_id=None), ArchiveTag(name="sem-gaveta")])
    db_session.flush()

    assert CurationRepository(db_session).count_subject_orphan_tags() == 2


def test_pending_proposals_are_counted_and_decided_ones_are_not(db_session) -> None:
    db_session.add_all(
        [
            ArchiveTagMergeProposal(fingerprint="f" * 64, canonical_name="loja", members=[], status="SUGGESTED"),
            ArchiveTagMergeProposal(fingerprint="g" * 64, canonical_name="casa", members=[], status="APPROVED"),
        ]
    )
    db_session.flush()

    assert CurationRepository(db_session).count_tag_merge_proposals() == 1


def test_pending_hierarchy_plans_are_counted(db_session) -> None:
    db_session.add_all(
        [
            ArchiveHierarchyNodePlan(code="BR PRADAP SMU", depth=1, status="SUGGESTED"),
            ArchiveHierarchyNodePlan(code="BR PRADAP SMU ED", depth=2, status="REJECTED"),
        ]
    )
    db_session.flush()

    assert CurationRepository(db_session).count_hierarchy_plans() == 1


def test_only_the_human_queue_of_a_conflict_is_counted(db_session) -> None:
    """
    A conflict the judge resolved with confidence is not work for the archivist.

    The count reads the persisted queue and not a live trigram scan: the scan compares thousands of
    tags against thousands of entities and measured 53 s on the real collection, which is not
    something a home screen may do.
    """
    db_session.add_all(
        [
            ArchiveAIReviewQueue(
                anomaly_type=AnomalyType.CROSS_DOMAIN_COLLISION,
                status=ArchiveReviewStatus.NEEDS_REVIEW,
                context_payload={"tag_id": 1, "entity_id": 2},
            ),
            ArchiveAIReviewQueue(
                anomaly_type=AnomalyType.CROSS_DOMAIN_COLLISION,
                status=ArchiveReviewStatus.AI_APPROVED,
                context_payload={"tag_id": 3, "entity_id": 4},
            ),
            ArchiveAIReviewQueue(
                anomaly_type=AnomalyType.SUBJECT_LOW_CONFIDENCE,
                status=ArchiveReviewStatus.NEEDS_REVIEW,
                context_payload={"tag_id": 5},
            ),
        ]
    )
    db_session.flush()

    repo = CurationRepository(db_session)
    assert repo.count_queue(AnomalyType.CROSS_DOMAIN_COLLISION) == 1
    assert repo.count_queue(AnomalyType.SUBJECT_LOW_CONFIDENCE) == 1


def test_the_inbox_serialises_every_queue_with_a_label_and_a_route(db_session) -> None:
    """The contract the front consumes: a key, a label, a number and where to go."""
    from scrinalia.domains.archive.services.curation_service import CurationService

    inbox = CurationService(CurationRepository(db_session)).inbox()

    assert len(inbox.queues) == len(QUEUE_CATALOGUE)
    assert all(queue.label and queue.route.startswith("/") for queue in inbox.queues)
    assert inbox.generated_at is not None
