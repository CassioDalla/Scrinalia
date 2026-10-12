from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scrinalia.core.base import Base

# Type-checker only, and load-bearing: the ``Mapped[...]`` strings below need this name. Keeping it
# inside the guard is what makes CodeQL's ``py/unsafe-cyclic-import`` finding a false positive
# (dismissed); ``testing/unit/quality/test_model_import_cycles.py`` fails if the cycle becomes real.
if TYPE_CHECKING:
    from .document import ArchiveDocument


class ArchiveEntity(Base):
    """
    Named Entities (People, Organizations, Locations).
    Discovered dynamically by spaCy or inserted manually.
    """

    __tablename__ = "archive_entities"

    entity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(
        secondary="archive_document_entities", back_populates="entities"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "idx_archive_entities_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        # The identity rule ``normalize_entity`` already declares — strip + lower — enforced where a
        # second row could appear. The case-sensitive unique index on the column cannot see ``Batel``
        # and ``batel`` as one name; this one can, and it is what stops ``get_or_create_entities``
        # (which inserts the normalized spelling) from creating a twin of a row stored in Title Case.
        Index("uix_archive_entities_name_normalized", func.lower(func.btrim(name)), unique=True),
    )
