from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.base import Base

if TYPE_CHECKING:
    from .document import ArchiveDocument


class ArchiveMacroCategory(Base):
    __tablename__ = "archive_macro_categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tags: Mapped[list["ArchiveTag"]] = relationship(back_populates="macro_category")


class ArchiveTag(Base):
    """
    Tags and Grouping Taxonomies.
    """

    __tablename__ = "archive_tags"

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    macro_category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_macro_categories.category_id", ondelete="SET NULL"), nullable=True, index=True
    )
    ai_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    descriptions: Mapped[list["ArchiveDocument"]] = relationship(
        secondary="archive_document_tags", back_populates="tags"
    )
    macro_category: Mapped["ArchiveMacroCategory"] = relationship(back_populates="tags")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "idx_archive_tags_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class ArchiveTypology(Base):
    __tablename__ = "archive_typologies"

    typology_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    context_description: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["ArchiveDocument"]] = relationship(back_populates="typology")
