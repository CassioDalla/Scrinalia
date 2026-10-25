from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from scrinalia.core.author import Author, author_columns
from scrinalia.core.content_hash import ContentHash
from scrinalia.core.logger import logger

from .models import RawData, ScrapeStatus, ScrapingQueue


def add(db: Session, description_id: str, origin_code: str | None = None) -> ScrapingQueue | None:
    """
    Adds a new document ID to the ingestion queue.

    Attempts to insert a new identifier into the database. If the ID already exists
    (UNIQUE constraint violation), the transaction is rolled back and the duplicate
    is silently ignored.

    Args:
        db (Session): Active SQLAlchemy session.
        description_id (str): Unique identifier of the document in the external source.
        origin_code (str | None): The origin that discovered it.

    Returns:
        ScrapingQueue | None: The inserted object instance, or None if
            the ID already exists or a database failure occurs.
    """

    item = ScrapingQueue(description_id=description_id, origin_code=origin_code)
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


def add_in_bulk(db: Session, description_id_list: list[str], origin_code: str | None = None) -> int:
    """
    Inserts a list of IDs into the batch processing queue (Bulk Insert).

    Uses the native PostgreSQL 'ON CONFLICT DO NOTHING' statement to ensure
    high I/O performance, ignoring ID rows that are already registered
    without aborting the transaction.

    Args:
        db (Session): Active SQLAlchemy session.
        description_id_list (list[str]): List containing the newly discovered IDs.
        origin_code (str | None): The origin that discovered the batch.

    Returns:
        int: The exact number of new records inserted into the database.
    """

    if not description_id_list:
        return 0

    data = [{"description_id": desc_id, "origin_code": origin_code} for desc_id in description_id_list]

    stmt = insert(ScrapingQueue).values(data)
    stmt = stmt.on_conflict_do_nothing(index_elements=["description_id"])
    stmt = stmt.returning(ScrapingQueue.description_id)
    inserted_ids = db.scalars(stmt).all()

    return len(inserted_ids)


def pending_conditions(
    discovered_after: datetime | None = None,
    scraped_before: datetime | None = None,
    ignore_status: list[ScrapeStatus] | None = None,
    origin_code: str | None = None,
) -> list[ColumnElement[bool]]:
    """
    The sliding-window policy, as one predicate.

    This is the **single definition** of "pending" in the ingestion queue: the run that takes a
    batch and the count that reports how much is left both build their statement from it, so a
    policy change cannot make the two disagree. It used to be written inline in ``get_from_queue``,
    which left a second counter with no honest way to answer "how many remain".
    """
    conditions: list[ColumnElement[bool]] = []

    if origin_code is not None:
        conditions.append(ScrapingQueue.origin_code == origin_code)

    if discovered_after is not None:
        conditions.append(ScrapingQueue.discovered_at >= discovered_after)

    if scraped_before is not None:
        conditions.append(
            or_(
                ScrapingQueue.last_scraped_at.is_(None),
                ScrapingQueue.last_scraped_at <= scraped_before,
            )
        )

    if ignore_status:
        conditions.append(ScrapingQueue.scrape_status.notin_(ignore_status))

    return conditions


def get_from_queue(
    db: Session,
    ignore_status: list[ScrapeStatus] | None = None,
    discovered_after: datetime | None = None,
    scraped_before: datetime | None = None,
    limit: int | None = None,
    origin_code: str | None = None,
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
        limit (int | None): Maximum number of rows this run may take. ``None`` is the whole queue.

    Returns:
        Sequence[ScrapingQueue]: List of queue entities ready for the Adapter.

    The ordering is what makes a limited run **resumable without starvation**: ``NULLS FIRST`` puts
    the never-tried IDs ahead of everything, and ``update_queue_status`` stamps ``last_scraped_at``
    in all three outcomes (done, transient failure, fatal), so the batch that just ran moves behind
    the ones that have not — even the batch that failed. The limit is applied to the statement the
    policy already filtered, never before it.
    """
    stmt = select(ScrapingQueue).where(
        *pending_conditions(discovered_after, scraped_before, ignore_status, origin_code)
    )
    stmt = stmt.order_by(ScrapingQueue.last_scraped_at.asc().nulls_first())

    if limit is not None:
        stmt = stmt.limit(limit)

    return db.scalars(stmt).all()


def count_pending(
    db: Session,
    ignore_status: list[ScrapeStatus] | None = None,
    discovered_after: datetime | None = None,
    scraped_before: datetime | None = None,
    origin_code: str | None = None,
) -> int:
    """
    How many queue rows the same policy still leaves pending.

    Built from :func:`pending_conditions`, so it is the run's own predicate and not a second
    definition of "pending" that drifts from it — the count a batch reports and the rows the next
    batch takes cannot disagree.
    """
    stmt = (
        select(func.count())
        .select_from(ScrapingQueue)
        .where(*pending_conditions(discovered_after, scraped_before, ignore_status, origin_code))
    )
    return int(db.scalar(stmt) or 0)


def count_processed(db: Session, origin_code: str | None = None, **_: object) -> int:
    """Queue rows the scrape finished, for the origin panel's ``processed`` number."""
    stmt = select(func.count()).select_from(ScrapingQueue).where(ScrapingQueue.scrape_status == ScrapeStatus.DONE)
    if origin_code is not None:
        stmt = stmt.where(ScrapingQueue.origin_code == origin_code)
    return int(db.scalar(stmt) or 0)


def count_failed(db: Session, origin_code: str | None = None, **_: object) -> int:
    """Queue rows whose failure is terminal for the policy: ``NOT_FOUND`` and ``FATAL_ERROR``."""
    stmt = (
        select(func.count())
        .select_from(ScrapingQueue)
        .where(ScrapingQueue.scrape_status.in_((ScrapeStatus.NOT_FOUND, ScrapeStatus.FATAL_ERROR)))
    )
    if origin_code is not None:
        stmt = stmt.where(ScrapingQueue.origin_code == origin_code)
    return int(db.scalar(stmt) or 0)


def count_raw_data(db: Session, origin_code: str | None = None, **_: object) -> int:
    """Raw payloads of one origin, for the manual origin's ``processed`` number."""
    stmt = select(func.count()).select_from(RawData)
    if origin_code is not None:
        stmt = stmt.where(RawData.origin_code == origin_code)
    return int(db.scalar(stmt) or 0)


def update_queue_status(
    db: Session,
    description_id: str,
    status: ScrapeStatus,
    error_msg: str | None = None,
    increment_retry: bool = False,
    origin_code: str | None = None,
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
    if origin_code is not None:
        stmt = stmt.where(ScrapingQueue.origin_code == origin_code)

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


def save_raw_data(
    db: Session,
    description_id: str,
    scraped_data: dict,
    *,
    origin_code: str | None = None,
    author: Author | None = None,
    raw_title: str | None = None,
) -> bool:
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
        origin_code (str | None): The origin that produced the payload.
        author (Author | None): Who sent it, when a person did.
        raw_title (str | None): The title for the quick-search column when the payload does not
            carry it under the scraper's ``title`` key. The manual form's payload does; the CSV's
            payload carries the file's label (``Título``), so the CSV import passes it here.

    Raises:
        Exception: Propagates any critical database error for the Orchestrator to handle.

    Returns:
        bool: True if the data was successfully inserted or verified.
    """
    title = raw_title if raw_title is not None else scraped_data.get("title")

    content_hash = ContentHash.of(scraped_data)

    values: dict[str, object] = {
        "description_id": description_id,
        "origin_code": origin_code,
        "raw_title": title,
        "payload": scraped_data,
        "content_hash": content_hash,
        **author_columns("created_by", author),
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
