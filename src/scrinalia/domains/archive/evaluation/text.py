"""The AI text one worker reads, composed by the same SQL expression the worker builds (ADR 0018).

The bench and the panel's trial both need "the text the model will see" for a set of descriptions,
and both would otherwise compose it themselves. The worker composes it in PostgreSQL
(``composed_text_sql``), subtracting the excerpts the archivist approved and normalizing whitespace;
a second composition in Python would measure a text the worker never sees. This module is the one
read-side mirror, and the bench's pinning test compares it with what ``worker_typology.execute``
hands to a fake engine.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveDocument
from scrinalia.domains.archive.repository.text_quality_repo import (
    TextQualityRepository,
    composed_text_sql,
)


def read_composed_text(db: Session, description_ids: Sequence[str], columns: Sequence[str]) -> dict[str, str]:
    """
    The text the worker reads, for these ids and columns.

    The scope is ``NER`` and the separator is ``". "``, the values ``worker_typology.execute`` uses;
    a caller that changes either changes the text the model is measured on. An empty id list answers
    an empty mapping instead of a query that would match every row.
    """
    if not description_ids:
        return {}
    rules = TextQualityRepository(db).get_active_rules("NER")
    text_expression = composed_text_sql(columns, rules, separator=". ")
    stmt = select(ArchiveDocument.description_id, text_expression).where(
        ArchiveDocument.description_id.in_(list(description_ids))
    )
    return {description_id: " ".join((text or "").split()) for description_id, text in db.execute(stmt).all()}
