from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.base import Base

from .enums import ArchiveReviewStatus

if TYPE_CHECKING:
    from .entity import ArchiveEntity
    from .taxonomy import ArchiveTag, ArchiveTypology


class ArchiveDocument(Base):
    """
    The final, cleaned and enriched document.

    This is the central database served to end users,
    fed by multiple asynchronous Artificial Intelligence workers.
    """

    __tablename__ = "archive_documents"

    description_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # --- Lineage and Origin ---
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    staging_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_thumbnail_uri: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Archival Metadata (ISAD-G) ---
    reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str | None] = mapped_column(Text, nullable=True)
    producers: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_bio_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_archival_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    archivist_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- NLP/AI Enrichment ---
    final_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_search_vector: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Example: {"ner_spacy_v1": "DONE", "mdeberta_tags": "PENDING"}
    execution_log: Mapped[dict] = mapped_column(JSONB, default=dict)
    typology_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("archive_typologies.typology_id", ondelete="SET NULL"), nullable=True, index=True
    )

    # --- Audit (Human-in-the-Loop) ---
    review_status: Mapped[ArchiveReviewStatus] = mapped_column(
        Enum(ArchiveReviewStatus, name="archive_review_status_enum", create_type=True),
        default=ArchiveReviewStatus.PENDING_AI,
        nullable=False,
        index=True,
    )
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    anomaly_reasons: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    # --- Relationships---
    entities: Mapped[list["ArchiveEntity"]] = relationship(
        secondary="archive_document_entities", back_populates="descriptions"
    )
    tags: Mapped[list["ArchiveTag"]] = relationship(secondary="archive_document_tags", back_populates="descriptions")
    typology: Mapped["ArchiveTypology"] = relationship(back_populates="documents")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # The GIN index is vital for the AI Workers' polling performance
        Index("ix_archive_exec_log", execution_log, postgresql_using="gin"),
    )
