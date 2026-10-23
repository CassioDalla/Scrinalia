"""
The typology's refusal queue, defined once.

The classifier does not always answer: a description whose best score stayed under the floor keeps
``typology_id`` NULL, and the column cannot say whether the run looked at it and declined or never
reached it at all. The refusal is written to ``archive_ai_review_queue`` as
``AnomalyType.TYPOLOGY_LOW_CONFIDENCE`` with the score it saw, and this module owns the two reads
that evidence exists for.

It is the same shape as :mod:`repository.subject_queue`, which answers the identical question for the
tags, and that is not a coincidence: the two axes record the same fact about the same kind of decision
and the archivist reads them on different screens.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue

#: The description a queue row is about. The row has no foreign key on purpose — the queue is a
#: snapshot of the evidence, like the merge proposals' member list — so the payload is the link.
DESCRIPTION_ID = "description_id"


def typology_low_confidence() -> ColumnElement[bool]:
    """
    Descriptions the typology classifier looked at and refused, with an open decision.

    The ``typology_id IS NULL`` half is not redundant: a curator may file a description afterwards,
    and nothing deletes the classifier's row when that happens. Reading the row alone would leave the
    read counting a description that already has a drawer — the evidence would outlive the decision.
    """
    return and_(
        ArchiveDocument.typology_id.is_(None),
        exists(
            select(1)
            .select_from(ArchiveAIReviewQueue)
            .where(
                ArchiveAIReviewQueue.anomaly_type == AnomalyType.TYPOLOGY_LOW_CONFIDENCE,
                ArchiveAIReviewQueue.status == ArchiveReviewStatus.NEEDS_REVIEW,
                ArchiveAIReviewQueue.context_payload[DESCRIPTION_ID].as_string() == ArchiveDocument.description_id,
            )
        ),
    )


def count_refusals(db: Session) -> int:
    """
    How many descriptions the classifier looked at and declined to place.

    The answer the bench's stored mode needs and cannot get from ``typology_id``: one query, no
    re-run, and it collapses the rows by description so a run repeated with ``force`` cannot inflate
    the number.
    """
    stmt = select(func.count()).select_from(ArchiveDocument).where(typology_low_confidence())
    return int(db.scalar(stmt) or 0)
