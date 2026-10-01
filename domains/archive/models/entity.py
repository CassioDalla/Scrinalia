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

from core.base import Base

if TYPE_CHECKING:
    from .document import ArchiveDocument


class ArchiveEntity(Base):
    """
    Entidades Nomeadas (Pessoas, Organizações, Locais).
    Descobertas dinamicamente pelo spaCy ou inseridas manualmente.
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
    )
