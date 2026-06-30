from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base


class ArchiveDocumentEntity(Base):
    __tablename__ = "archive_document_entities"
    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("archive_documents.description_id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archive_entities.entity_id", ondelete="CASCADE"), primary_key=True
    )
    __table_args__ = (UniqueConstraint("description_id", "entity_id", name="uix_description_entity"),)


class ArchiveDocumentTag(Base):
    __tablename__ = "archive_document_tags"
    description_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("archive_documents.description_id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archive_tags.tag_id", ondelete="CASCADE"), primary_key=True
    )
    __table_args__ = (UniqueConstraint("description_id", "tag_id", name="uix_description_tag"),)
