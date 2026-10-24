"""
The typology's refusal queue, defined once.

The classifier does not always answer: a description whose best score stayed under the floor keeps
``typology_id`` NULL, and the column cannot say whether the run looked at it and declined or never
reached it at all. The refusal is written to ``archive_ai_review_queue`` as
``AnomalyType.TYPOLOGY_LOW_CONFIDENCE`` with the score it saw, and this module owns the reads that
evidence exists for: the predicate, the count and the page the screen shows.

It is the same shape as :mod:`repository.subject_queue`, which answers the identical question for the
tags, and that is not a coincidence: the two axes record the same fact about the same kind of decision
and the archivist reads them on different screens.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, func, select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.archive.models.governance import AnomalyType, ArchiveAIReviewQueue
from scrinalia.domains.archive.schemas.typology_schema import TypologyRefusalRow

#: The description a queue row is about. The row has no foreign key on purpose — the queue is a
#: snapshot of the evidence, like the merge proposals' member list — so the payload is the link.
DESCRIPTION_ID = "description_id"


def _open_evidence() -> Select[int, Any, str | None, float | None]:
    """
    The queue rows that still describe an open typology decision, one row per run.

    The anomaly type, the status and the payload key are written here once. The predicate, the count
    and the page all compose this select, so a read cannot quietly ask a different question from the
    one the rest of the system answers.
    """
    return select(
        ArchiveAIReviewQueue.id,
        ArchiveAIReviewQueue.context_payload[DESCRIPTION_ID].as_string().label(DESCRIPTION_ID),
        ArchiveAIReviewQueue.llm_decision,
        ArchiveAIReviewQueue.llm_confidence,
    ).where(
        ArchiveAIReviewQueue.anomaly_type == AnomalyType.TYPOLOGY_LOW_CONFIDENCE,
        ArchiveAIReviewQueue.status == ArchiveReviewStatus.NEEDS_REVIEW,
    )


def typology_low_confidence() -> ColumnElement[bool]:
    """
    Descriptions the typology classifier looked at and refused, with an open decision.

    The ``typology_id IS NULL`` half is not redundant: a curator may file a description afterwards,
    and nothing deletes the classifier's row when that happens. Reading the row alone would leave the
    read counting a description that already has a drawer — the evidence would outlive the decision.
    """
    evidence = _open_evidence().subquery()
    return and_(
        ArchiveDocument.typology_id.is_(None),
        exists(select(1).select_from(evidence).where(evidence.c.description_id == ArchiveDocument.description_id)),
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


def refusal_page_statement(limit: int, offset: int) -> Select[str, str, str | None, date | None, str | None, Any, Any]:
    """
    The statement behind one page of the refusal queue, nearest miss first.

    Exposed so the SQL that the API runs is the SQL a measurement or a shape test inspects: a
    read-only plan benchmark that rebuilt the query would be measuring a second definition.

    ``row_number`` collapses the rows a repeated run left for the same description and keeps the
    **latest** one: it is the evidence of the run that just refused, while a higher score from an
    older run may belong to another floor or another model. The score decides the order because a
    description at 0.39 and one at 0.05 are not the same decision, and the population just under the
    floor is the one that decides whether the floor is right.

    The page is built on :func:`_open_evidence` and filtered by :func:`typology_low_confidence`, the
    same predicate ``count_refusals`` counts, so the total and the rows cannot disagree.
    """
    evidence = _open_evidence().subquery()
    latest = select(
        evidence.c.description_id,
        evidence.c.llm_decision.label("guessed_label"),
        evidence.c.llm_confidence.label("ai_confidence_score"),
        func.row_number()
        .over(
            partition_by=evidence.c.description_id,
            order_by=evidence.c.id.desc(),
        )
        .label("position"),
    ).subquery()
    return (
        select(
            ArchiveDocument.description_id,
            ArchiveDocument.original_title,
            ArchiveDocument.final_title,
            ArchiveDocument.document_date,
            ArchiveDocument.reference_code,
            latest.c.guessed_label,
            latest.c.ai_confidence_score,
        )
        .join(latest, latest.c.description_id == ArchiveDocument.description_id)
        .where(latest.c.position == 1, typology_low_confidence())
        # ``description_id`` is the tie-break, not decoration: two equal scores would otherwise let
        # PostgreSQL return a different page on every request, and the screen would page over rows
        # it had already shown.
        .order_by(latest.c.ai_confidence_score.desc().nulls_last(), ArchiveDocument.description_id)
        .limit(limit)
        .offset(offset)
    )


def read_refusals(db: Session, limit: int, offset: int) -> list[TypologyRefusalRow]:
    """One page of the refused descriptions; the statement is :func:`refusal_page_statement`."""
    stmt = refusal_page_statement(limit, offset)
    return [TypologyRefusalRow.model_validate(dict(row)) for row in db.execute(stmt).mappings().all()]
