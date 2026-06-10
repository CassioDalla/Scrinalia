from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SilverDescriptionModel(Base):
    __tablename__ = "silver_descriptions"

    description_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    bronze_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadados da Norma ISAD(G)
    reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimension_support: Mapped[str | None] = mapped_column(Text, nullable=True)
    producers: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_bio_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_archival_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    appraisal_destruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    accruals: Mapped[str | None] = mapped_column(Text, nullable=True)
    arrangement: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    reproduction_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    physical_characteristics: Mapped[str | None] = mapped_column(Text, nullable=True)
    finding_aids: Mapped[str | None] = mapped_column(Text, nullable=True)
    originals_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    copies_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_units: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    conservation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    general_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archivist_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_conventions: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_dates: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexing_points: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
