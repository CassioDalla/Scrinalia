from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.content_hash import ContentHash
from core.logger import logger

from .models import RawData, ScrapeStatus, ScrapingQueue


def add(db: Session, description_id: str) -> ScrapingQueue | None:
    """
    Adds a new document ID to the ingestion queue.

    Attempts to insert a new identifier into the database. If the ID already exists
    (UNIQUE constraint violation), the transaction is rolled back and the duplicate
    is silently ignored.

    Args:
        db (Session): Active SQLAlchemy session.
        description_id (str): Unique identifier of the document in the external source.

    Returns:
        ScrapingQueue | None: The inserted object instance, or None if
            the ID already exists or a database failure occurs.
    """

    item = ScrapingQueue(description_id=description_id)
    try:
        # A savepoint keeps the caller's transaction usable when the ID is duplicated.
        with db.begin_nested():
            db.add(item)
            db.flush()
        return item

    except IntegrityError:
        logger.debug(f"Description with ID {description_id} already exists in the database. Ignored.")
        return None

    except Exception as e:
        logger.critical(f"Critical database error when inserting description_id {description_id}: {e}")
        return None


def add_in_bulk(db: Session, description_id_list: list[str]) -> int:
    """
    Inserts a list of IDs into the batch processing queue (Bulk Insert).

    Uses the native PostgreSQL 'ON CONFLICT DO NOTHING' statement to ensure
    high I/O performance, ignoring ID rows that are already registered
    without aborting the transaction.

    Args:
        db (Session): Active SQLAlchemy session.
        description_id_list (list[str]): List containing the newly discovered IDs.

    Returns:
        int: The exact number of new records inserted into the database.
    """

    if not description_id_list:
        return 0

    data = [{"description_id": desc_id} for desc_id in description_id_list]

    stmt = insert(ScrapingQueue).values(data)
    stmt = stmt.on_conflict_do_nothing(index_elements=["description_id"])
    stmt = stmt.returning(ScrapingQueue.description_id)
    inserted_ids = db.scalars(stmt).all()

    return len(inserted_ids)


def get_from_queue(
    db: Session,
    ignore_status: list[ScrapeStatus] | None = None,
    discovered_after: datetime | None = None,
    scraped_before: datetime | None = None,
) -> Sequence[ScrapingQueue]:
    """
    Retrieves a batch of documents from the queue pending detail extraction.

    Applies 'Sliding Window' business rules, returning IDs that
    have never been processed (NULLS FIRST) or that have exceeded their
    time-to-live (TTL) and require re-checking for updates.

    Args:
        db (Session): Active SQLAlchemy session.
        ignore_status (list[ScrapeStatus] | None): List of statuses to exclude from results.
        discovered_after (datetime | None): Discovery time window filter.
        scraped_before (datetime | None): Obsolescence (TTL) time window filter.

    Returns:
        Sequence[ScrapingQueue]: List of queue entities ready for the Adapter.
    """
    stmt = select(ScrapingQueue)

    if discovered_after is not None:
        stmt = stmt.where(ScrapingQueue.discovered_at >= discovered_after)

    if scraped_before is not None:
        stmt = stmt.where(
            or_(
                ScrapingQueue.last_scraped_at.is_(None),
                ScrapingQueue.last_scraped_at <= scraped_before,
            )
        )

    if ignore_status:
        stmt = stmt.where(ScrapingQueue.scrape_status.notin_(ignore_status))

    stmt = stmt.order_by(ScrapingQueue.last_scraped_at.asc().nulls_first())

    return db.scalars(stmt).all()


def update_queue_status(
    db: Session,
    description_id: str,
    status: ScrapeStatus,
    error_msg: str | None = None,
    increment_retry: bool = False,
) -> bool:
    """
    Updates the state of a document in the queue following an ingestion attempt.

    Executes an atomic UPDATE command directly on the database, recording
    the exact timestamp of the operation. Manages the transient failure count (retries)
    and captures error logs provided by the Adapters.

    Args:
        db (Session): Active SQLAlchemy session.
        description_id (str): Unique document identifier.
        status (ScrapeStatus): New status to be applied (e.g., DONE, FATAL_ERROR).
        error_msg (str | None): Error message originating from the domain or adapter.
        increment_retry (bool): If True, increments the failure counter for the ID by 1.

    Returns:
        bool: True if the queue was successfully updated, False if the ID does not exist.
    """
    now = datetime.now(UTC)
    stmt = update(ScrapingQueue).where(ScrapingQueue.description_id == description_id)

    if status == ScrapeStatus.DONE:
        # Success: Resets the retry counter
        stmt = stmt.values(scrape_status=status, last_scraped_at=now, retry_count=0)
    elif increment_retry:
        # Transient failure: Increment +1
        stmt = stmt.values(
            scrape_status=status,
            last_scraped_at=now,
            retry_count=ScrapingQueue.retry_count + 1,
            last_error_message=error_msg,
        )
    else:
        # Fatal error: Only changes the status; does not affect the counter.
        stmt = stmt.values(scrape_status=status, last_scraped_at=now, last_error_message=error_msg)

    stmt = stmt.returning(ScrapingQueue.description_id)

    updated_id = db.scalar(stmt)

    if updated_id is None:
        logger.warning(f"Attempt to update status of non-existent ID:{description_id}")
        return False

    return True


def save_raw_data(db: Session, description_id: str, scraped_data: dict) -> bool:
    """
    Persists the raw data extracted by the Adapter in the Ingestion layer.

    Calculates an SHA-256 hash of the received payload for idempotency control.
    Uses PostgreSQL's 'UPSERT' (ON CONFLICT DO UPDATE) with a conditional
    to skip the physical disk update if the hash of the captured content
    matches the one already in the database.

    Args:
        db (Session): Active SQLAlchemy session.
        description_id (str): Unique identifier of the document in the external source.
        scraped_data (dict): Raw dictionary containing the extracted metadata.

    Raises:
        Exception: Propagates any critical database error for the Orchestrator to handle.

    Returns:
        bool: True if the data was successfully inserted or verified.
    """
    raw_title = scraped_data.get("title")

    content_hash = ContentHash.of(scraped_data)

    values = {
        "description_id": description_id,
        "raw_title": raw_title,
        "payload": scraped_data,
        "content_hash": content_hash,
    }

    stmt = insert(RawData).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["description_id"],
        set_={
            "raw_title": stmt.excluded.raw_title,
            "payload": stmt.excluded.payload,
            "content_hash": stmt.excluded.content_hash,
            "updated_at": func.now(),
        },
        where=(RawData.content_hash != stmt.excluded.content_hash),
    )
    db.execute(stmt)
    return True
