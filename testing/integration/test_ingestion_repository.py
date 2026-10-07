from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from scrinalia.domains.ingestion.models import ScrapeStatus, ScrapingQueue
from scrinalia.domains.ingestion.repository import add, add_in_bulk, get_from_queue, update_queue_status

# ==========================================
# 1. SIMPLE INSERT TESTS (ADD)
# ==========================================


def test_add_success(use_test_db, db_session):
    """Guarantees that a new document is correctly inserted into the queue."""
    item = add(db_session, "doc_123")

    assert item is not None
    assert item.description_id == "doc_123"
    assert item.scrape_status == ScrapeStatus.PENDING
    assert item.retry_count == 0


def test_add_duplicate_integrity_error(use_test_db, db_session):
    """Tests the database protection. If the ID already exists, it must roll back softly and return None."""
    # Original insert
    add(db_session, "doc_duplicado")

    # Duplicate attempt
    repeated_item = add(db_session, "doc_duplicado")

    assert repeated_item is None
    # Guarantees that the database remains operational after the rollback
    count = db_session.query(ScrapingQueue).count()
    assert count == 1


# ==========================================
# 2. BULK INSERT TESTS
# ==========================================


def test_add_in_bulk_success(use_test_db, db_session):
    """Tests the fast insertion of multiple IDs at once."""
    ids = ["doc_1", "doc_2", "doc_3"]
    inserted_count = add_in_bulk(db_session, ids)

    assert inserted_count == 3
    db_count = db_session.query(ScrapingQueue).count()
    assert db_count == 3


def test_add_in_bulk_ignore_duplicates(use_test_db, db_session):
    """Tests ON CONFLICT DO NOTHING. Repeated IDs must be silently ignored."""
    # First batch
    add_in_bulk(db_session, ["doc_A", "doc_B"])

    # Second batch (doc_B already exists, doc_C is new)
    new_count = add_in_bulk(db_session, ["doc_B", "doc_C"])

    # Only doc_C must be counted as a new insert
    assert new_count == 1
    total_count = db_session.query(ScrapingQueue).count()
    assert total_count == 3


def test_add_in_bulk_empty_list(use_test_db, db_session):
    """Guarantees that sending an empty list does not break the SQL."""
    count = add_in_bulk(db_session, [])
    assert count == 0


# ==========================================
# 3. RETRIEVAL TESTS (SLIDING WINDOW)
# ==========================================


def test_get_from_queue_nulls_first(use_test_db, db_session):
    """Guarantees that documents that were NEVER scraped (Null) come first in the queue."""
    today = datetime.now(UTC)

    old_doc = ScrapingQueue(description_id="doc_velho", last_scraped_at=today - timedelta(days=5))
    new_doc = ScrapingQueue(description_id="doc_novo", last_scraped_at=today)
    never_scraped_doc = ScrapingQueue(description_id="doc_virgem", last_scraped_at=None)  # Never scraped

    db_session.add_all([old_doc, new_doc, never_scraped_doc])
    db_session.commit()

    queue = get_from_queue(db_session)

    assert len(queue) == 3
    # The ordering must be: NULLS FIRST, then from oldest to newest
    assert queue[0].description_id == "doc_virgem"
    assert queue[1].description_id == "doc_velho"
    assert queue[2].description_id == "doc_novo"


def test_get_from_queue_ignore_status(use_test_db, db_session):
    """Guarantees that ignored statuses do not pollute the queue search."""
    pending_doc = ScrapingQueue(description_id="doc_p", scrape_status=ScrapeStatus.PENDING)
    fatal_doc = ScrapingQueue(description_id="doc_f", scrape_status=ScrapeStatus.FATAL_ERROR)

    db_session.add_all([pending_doc, fatal_doc])
    db_session.commit()

    queue = get_from_queue(db_session, ignore_status=[ScrapeStatus.FATAL_ERROR])

    assert len(queue) == 1
    assert queue[0].description_id == "doc_p"


def test_get_from_queue_sliding_window(use_test_db, db_session):
    """Tests the time window filters (scraped_before)."""
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)
    last_week = now - timedelta(days=7)

    recent_doc = ScrapingQueue(description_id="doc_recente", last_scraped_at=yesterday)
    expired_doc = ScrapingQueue(description_id="doc_expirado", last_scraped_at=last_week)

    db_session.add_all([recent_doc, expired_doc])
    db_session.commit()

    # Requests documents that were scraped BEFORE 3 days ago
    cutoff = now - timedelta(days=3)
    queue = get_from_queue(db_session, scraped_before=cutoff)

    assert len(queue) == 1
    assert queue[0].description_id == "doc_expirado"


# ==========================================
# 4. STATUS UPDATE TESTS (UPDATE)
# ==========================================


def test_update_queue_status_success(use_test_db, db_session):
    """Guarantees that a success (DONE) resets the retries and records the exact time."""
    # Create a doc with past errors
    doc = ScrapingQueue(description_id="doc_1", retry_count=2, scrape_status=ScrapeStatus.PENDING)
    db_session.add(doc)
    db_session.commit()

    result = update_queue_status(db_session, "doc_1", ScrapeStatus.DONE)
    assert result is True

    db_session.expire_all()
    updated_doc = db_session.execute(select(ScrapingQueue).filter_by(description_id="doc_1")).scalar_one()

    assert updated_doc.scrape_status == ScrapeStatus.DONE
    assert updated_doc.retry_count == 0  # Reset!
    assert updated_doc.last_scraped_at is not None


def test_update_queue_status_increment_retry(use_test_db, db_session):
    """Tests a transient error: it must add +1 to the count and save the error log."""
    doc = ScrapingQueue(description_id="doc_2", retry_count=1)
    db_session.add(doc)
    db_session.commit()

    update_queue_status(db_session, "doc_2", ScrapeStatus.NETWORK_ERROR, error_msg="Timeout 504", increment_retry=True)

    db_session.expire_all()
    updated_doc = db_session.execute(select(ScrapingQueue).filter_by(description_id="doc_2")).scalar_one()

    assert updated_doc.retry_count == 2  # Incremented 1 + 1
    assert updated_doc.scrape_status == ScrapeStatus.NETWORK_ERROR
    assert updated_doc.last_error_message == "Timeout 504"


def test_update_queue_status_fatal_error(use_test_db, db_session):
    """Tests a definitive error: it changes the status and error, but does NOT change the retry count."""
    doc = ScrapingQueue(description_id="doc_3", retry_count=3)
    db_session.add(doc)
    db_session.commit()

    update_queue_status(db_session, "doc_3", ScrapeStatus.FATAL_ERROR, error_msg="404 Not Found", increment_retry=False)

    db_session.expire_all()
    updated_doc = db_session.execute(select(ScrapingQueue).filter_by(description_id="doc_3")).scalar_one()

    assert updated_doc.retry_count == 3  # Remains intact
    assert updated_doc.scrape_status == ScrapeStatus.FATAL_ERROR
    assert updated_doc.last_error_message == "404 Not Found"


def test_update_queue_status_not_found(use_test_db, db_session):
    """Guarantees that trying to update an ID that does not exist safely returns False."""
    result = update_queue_status(db_session, "id_fantasma", ScrapeStatus.DONE)
    assert result is False
