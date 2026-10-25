import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base


class IngestionOrigin(Base):
    """
    One origin this installation reads, with its lifecycle, its configuration and its agenda.

    The *definition* of an origin — its adapter, the shape of its configuration and the labels of
    its payload — lives in code (``domains/ingestion/origin_registry.py`` and ``origins.py``). This
    table is what an operator changes without a deploy: whether the origin is enabled, the URLs or
    path it reads, the run policy its scheduled executions inherit, and the cron/zone of that
    agenda.

    It is a table and not a settings row for the same reason the collection vocabulary is: the
    person who owns the origin has to be able to point it at another site, pause it and schedule it
    from the screen, and the origin has a lifecycle that outlives a process.

    ``code`` is the foreign key in spirit to the code registry, without a database foreign key:
    origins are code, and a row whose code left the registry stays readable — exactly like a run
    whose worker left the catalogue. It simply cannot run.
    """

    __tablename__ = "ingestion_origins"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    #: The adapter's own configuration (URLs, path, delimiter). Validated by the origin's
    #: ``config_model`` on every read and write; never a place for a secret.
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: The run policy a scheduled execution inherits (pages, windows, retries). The per-run request
    #: overrides it; a field left out follows the worker's signature default.
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: The five-field cron, evaluated in ``timezone``. ``NULL`` means the origin has no agenda and
    #: is only reachable through a manual run.
    cron: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: The account behind the name above; ``SET NULL`` so a deactivated account keeps its name on
    #: the decision, like every other author link in the schema.
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # The scheduler's due query: enabled origins with an agenda whose next run is due.
        Index("ix_ingestion_origin_next_run_at", "next_run_at"),
    )


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
    #: The origin that discovered this identifier. Nullable only for the rows written before plural
    #: ingestion; the migration backfills them with the reference origin. The business key stays
    #: ``description_id`` (global across origins), so an adapter that can collide namespaces its ids.
    origin_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    scrape_status: Mapped[ScrapeStatus] = mapped_column(
        Enum(ScrapeStatus, name="scrape_status_enum", create_type=False), default=ScrapeStatus.PENDING
    )
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    last_error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # The per-origin queue read: filter by origin, order by ``last_scraped_at NULLS FIRST``.
        Index("ix_scraping_queue_origin_last_scraped", "origin_code", "last_scraped_at"),
    )


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
    #: The origin whose adapter produced this payload. Nullable only for the rows written before
    #: plural ingestion; new writes always set it.
    origin_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    raw_title: Mapped[str | None] = mapped_column(String(500))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    #: The person who typed the record, when the origin is ``manual``. A scraper writes no author:
    #: its author is the origin itself, which the column above already names.
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # The manual origin's pending read: raw records of one origin, by description id.
        Index("ix_raw_data_origin_description", "origin_code", "description_id"),
    )
