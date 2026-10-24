from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scrinalia.core.base import Base

from .enums import ArchiveEntityOrigin

# Type-checker only, and load-bearing: the ``Mapped[...]`` strings below need these names. Keeping
# them inside the guard is what makes CodeQL's ``py/unsafe-cyclic-import`` finding a false positive
# (dismissed); ``testing/unit/quality/test_model_import_cycles.py`` fails if the cycle becomes real.
if TYPE_CHECKING:
    from .document import ArchiveDocument
    from .entity import ArchiveEntity


class ArchiveDocumentEntity(Base):
    """
    One named entity attached to one description, and who attached it.

    The row used to be only the composite key, so a surviving link could not say whether the
    extractor wrote it and nobody looked, or whether a person confirmed it: the two were the same
    row (#135). ``origin`` is a fact about this link and never a permission — what keeps the AI from
    rewriting a curated description is the document's ``HUMAN_APPROVED``, and the extraction path
    inserts with ``ON CONFLICT DO NOTHING`` so it cannot touch a link already there.
    """

    __tablename__ = "archive_document_entities"
    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("archive_documents.description_id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archive_entities.entity_id", ondelete="CASCADE"), primary_key=True
    )
    origin: Mapped[ArchiveEntityOrigin] = mapped_column(
        Enum(ArchiveEntityOrigin, name="archive_entity_origin"), nullable=False
    )
    #: When the link was written. ``NULL`` on the rows that predate the column: the moment is
    #: unknown, and the migration backfills the origin as ``UNKNOWN`` rather than stamping "now".
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["ArchiveDocument"] = relationship(back_populates="entity_links")
    entity: Mapped["ArchiveEntity"] = relationship()


class ArchiveDocumentTag(Base):
    __tablename__ = "archive_document_tags"
    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("archive_documents.description_id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archive_tags.tag_id", ondelete="CASCADE"), primary_key=True
    )
