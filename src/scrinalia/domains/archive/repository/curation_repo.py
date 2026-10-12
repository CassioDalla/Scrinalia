"""Read-only aggregation behind the curator's work list (``GET /curation/inbox``)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import (
    ArchiveDescriptionLevel,
    ArchiveDocument,
    ArchiveHierarchyNodePlan,
    ArchiveReviewStatus,
    ArchiveTag,
    ArchiveTagMergeProposal,
)
from scrinalia.domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue
from scrinalia.domains.archive.repository.subject_queue import subject_low_confidence, subject_pending

#: Status a proposal/plan carries while it is still waiting for a human verdict. Semantics owned by
#: the ``chk_*_status`` constraints of the two catalogues, repeated here as a literal because it is
#: a *filter on stored data*, not a second definition of the vocabulary.
SUGGESTED = "SUGGESTED"


class CurationRepository:
    """
    Counts the pending queues of the collection.

    Nothing here is new logic: every number is a predicate some screen already applies. What the
    repository adds is the *aggregation*, so the curator's home is one request instead of seven,
    and the numbers are read from indexed columns rather than by calling each screen's route.

    The tag/entity collision count is read from ``archive_ai_review_queue`` and **not** recomputed
    with a trigram scan: the live scan compares 6 142 tags against 3 808 entities and measured
    **53 s** (23.4 M pairs, nested loop) on the real collection. The judged pairs are already
    persisted by ``worker_resolve_tag_entity_conflict``, so the count is an indexed one.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def _count_documents(self, *conditions: object) -> int:
        stmt = select(func.count()).select_from(ArchiveDocument).where(*conditions)  # type: ignore[arg-type]
        return int(self.db.scalar(stmt) or 0)

    def count_hierarchy_orphans(self) -> int:
        """
        Descriptions the arrangement still cannot place.

        The same predicate the hierarchy diagnosis reports as ``ORPHAN``: a node with no parent
        whose level demands one, plus the ones with no level at all, which cannot be judged.
        """
        return self._count_documents(
            ArchiveDocument.parent_id.is_(None),
            or_(
                ArchiveDocument.level_id.is_(None),
                ArchiveDocument.level_ref.has(ArchiveDescriptionLevel.requires_parent.is_(True)),  # type: ignore[attr-defined]
            ),
        )

    def count_hierarchy_plans(self) -> int:
        """Rungs the slicer proposed and no human has decided yet."""
        stmt = (
            select(func.count())
            .select_from(ArchiveHierarchyNodePlan)
            .where(ArchiveHierarchyNodePlan.status == SUGGESTED)
        )
        return int(self.db.scalar(stmt) or 0)

    def count_tag_merge_proposals(self) -> int:
        """Clusters of spellings waiting for an approve/reject verdict."""
        stmt = (
            select(func.count()).select_from(ArchiveTagMergeProposal).where(ArchiveTagMergeProposal.status == SUGGESTED)
        )
        return int(self.db.scalar(stmt) or 0)

    def count_subject_orphan_tags(self) -> int:
        """
        Tags whose subject nobody has decided yet: no drawer, no verdict, no facet.

        Not ``macro_category_id IS NULL``, which is what it used to be. That column holds the
        *absence* of a classification and the human verdict "this tag is not a subject" in the same
        value, so a count built on it alone could never reach zero and the card was a debt the
        archivist could not pay. The predicate is ``subject_queue.subject_pending()``, imported
        rather than repeated: the catalogue's ``situacao=PENDING`` filter has to answer the same
        number, and the test that drives both routes is what makes the pair impossible to drift.
        """
        stmt = select(func.count()).select_from(ArchiveTag).where(subject_pending())
        return int(self.db.scalar(stmt) or 0)

    def count_subject_low_confidence_tags(self) -> int:
        """
        Tags the classifier left below its floor and no human has decided yet.

        Counted as **tags**, not as queue rows. ``worker_macro_category`` inserts one row per run in
        which the label set changed, so a tag can accumulate several, and counting rows answered "2"
        for a single decision to take. The other half is the ``PENDING`` condition inside
        ``subject_low_confidence()``: nothing deletes the queue row when the archivist files the tag,
        so reading the row alone would keep counting work that is already done.
        """
        stmt = select(func.count()).select_from(ArchiveTag).where(subject_low_confidence())
        return int(self.db.scalar(stmt) or 0)

    def count_queue(self, anomaly_type: AnomalyType) -> int:
        """
        Items of the AI review queue still waiting for a human.

        A plain row count, right for the conflict queue: ``worker_resolve_tag_entity_conflict``
        writes one row per pair. The low-confidence queue is counted per **tag** instead — see
        ``count_subject_low_confidence_tags`` — because there a row is evidence of a run and the
        decision is about a tag.
        """
        stmt = (
            select(func.count())
            .select_from(ArchiveAIReviewQueue)
            .where(
                ArchiveAIReviewQueue.anomaly_type == anomaly_type,
                ArchiveAIReviewQueue.status == ArchiveReviewStatus.NEEDS_REVIEW,
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def count_anomalies(self) -> int:
        """Documents the quality validator flagged."""
        return self._count_documents(ArchiveDocument.is_anomaly.is_(True))

    def count_unreviewed_documents(self) -> int:
        """Documents no human has looked at: the backlog of the collection."""
        return self._count_documents(ArchiveDocument.review_status == ArchiveReviewStatus.PENDING_AI)

    def count_pending(self) -> dict[str, int]:
        """Every queue of the work list, one query per queue, all on indexed columns."""
        return {
            "hierarchy_orphans": self.count_hierarchy_orphans(),
            "hierarchy_plans": self.count_hierarchy_plans(),
            "tag_merge_proposals": self.count_tag_merge_proposals(),
            "cross_domain_conflicts": self.count_queue(AnomalyType.CROSS_DOMAIN_COLLISION),
            "subject_low_confidence": self.count_subject_low_confidence_tags(),
            "orphan_subject_tags": self.count_subject_orphan_tags(),
            "anomalies": self.count_anomalies(),
            "unreviewed_documents": self.count_unreviewed_documents(),
        }
