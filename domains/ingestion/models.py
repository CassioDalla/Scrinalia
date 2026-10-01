import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base


class ScrapeStatus(enum.Enum):
    """
    Represents the current state of a document in the extraction queue.

    - PENDING: In the queue, awaiting processing.
    - DONE: Successfully extracted and saved to the RawData table.
    - NETWORK_ERROR: Transient failure (timeout, connection loss). Allows retries.
    - NOT_FOUND: 404 error. The document no longer exists in the source system.
    - FATAL_ERROR: Permanent error (malformed HTML, retry limit exceeded).
    """

    PENDING = "PENDING"
    DONE = "DONE"
    NETWORK_ERROR = "NETWORK_ERROR"
    NOT_FOUND = "NOT_FOUND"
    FATAL_ERROR = "FATAL_ERROR"


class ScrapingQueue(Base):
    """
    Control table (queue) for the data ingestion engine.

    Stores unique identifiers found in the legacy repository and manages
    the extraction state for each, applying sliding window concepts and
    concurrency control (retries).

    Attributes:
        description_id: The legacy document ID (business key).
        scrape_status: The current processing state of this ID.
        discovered_at: Date the ID was first found in the repository.
        last_scraped_at: Date of the last extraction attempt (successful or failed).
        retry_count: Number of consecutive transient failures.
        last_error_message: Log of the last error captured to facilitate debugging.
    """

    __tablename__ = "scraping_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    description_id: Mapped[str] = mapped_column(String(60), unique=True)
    scrape_status: Mapped[ScrapeStatus] = mapped_column(
        Enum(ScrapeStatus, name="scrape_status_enum", create_type=False), default=ScrapeStatus.PENDING
    )
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    last_error_message: Mapped[str | None] = mapped_column(Text)


class RawData(Base):
    """
    Raw data repository.

    Stores the exact payload returned by the adapters,
    without any processing, typing, or cleaning, ensuring the preservation
    of the original data for future restructuring in the Silver (Staging) layer.

    Attributes:
        description_id: The legacy document ID, used as a join key.
        content_hash: Cryptographic hash (e.g., SHA-256) of the payload for
            idempotency control and detection of silent updates at the source.
        raw_title: Original, unprocessed title for quick searches or debugging.
        payload: Complete dictionary containing all extracted metadata.
    """

    __tablename__ = "raw_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    description_id: Mapped[str] = mapped_column(String(60), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    raw_title: Mapped[str | None] = mapped_column(String(500))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
