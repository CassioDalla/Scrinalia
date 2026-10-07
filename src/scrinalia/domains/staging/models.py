from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base


class StagingDocument(Base):
    """
    Represents a structured and typed archival document within the Staging Domain.

    This entity receives raw data (RawData) from the ingestion Domain and
    transforms it into strict relational columns, mapping it to the archival
    descriptive model based on the ISAD(G) standard.

    It serves as the single source of sanitized truth before the document
    proceeds to Artificial Intelligence processing on Archive Domain.

    Attributes:
        description_id: The unique legacy identifier from the source system.
        raw_content_hash: Lineage hash. Links this structured version to the
             exact raw version that generated it. Essential for detecting if the document needs reprocessing.
        title: Main title of the document.
        document_date: Normalized document date (when applicable and validatable).
        raw_metadata: Backup copy (JSON) containing original unmapped keys
            or edge cases that did not fit the standard ISAD(G) schema.
    """

    __tablename__ = "staging_documents"

    description_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    raw_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumb_down_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata ISAD(G)
    reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Arrangement declared by the source. Optional by design: an origin that does not send it does
    #: not break the load, and a parent that has not arrived yet leaves the description orphan and
    #: *marked* instead of failing the batch (the origin may deliver the child before the parent).
    parent_reference_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    hierarchy_path: Mapped[str | None] = mapped_column(Text, nullable=True)
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
