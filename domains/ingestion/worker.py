from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from core.database import get_db
from core.logger import logger
from domains.archive.runner_config import IngestionRunnerConfig
from domains.ingestion import repository
from domains.ingestion.models import ScrapeStatus
from domains.ingestion.ports import (
    AdapterFatalError,
    AdapterNetworkError,
    AdapterNotFoundError,
    IDetailAdapter,
    IDiscoveryAdapter,
)


def run_discovery_job(db_session: Session, adapter: IDiscoveryAdapter, max_pages: int | None = None):
    """
    Orchestrates the Ingestion discovery phase, retrieving new IDs from the data source.

    Uses a discovery adapter (IDiscoveryAdapter) to iterate over the
    source (web pages, spreadsheets, APIs) and inserts new identifiers
    into the Processing Queue in batches (bulk insert).

    Args:
        db_session (Session): Active SQLAlchemy session.
        adapter (IDiscoveryAdapter): Instance of the adapter responsible for retrieving IDs.
        max_pages (int | None, optional): Limit on the number of iterations/pages to process.
    """

    logger.info("🚀 Starting ID discovery job...")

    total_inserted = 0
    for batch_ids in adapter.fetch_new_ids(max_pages=max_pages):
        inserted_count = repository.add_in_bulk(db_session, batch_ids)
        total_inserted += inserted_count

        if inserted_count > 0:
            logger.success(f"🔥 +{inserted_count} new documents in the queue.")

    if total_inserted == 0:
        logger.warning("No new IDs were found in this execution.")


def run_detail_scraping_job(
    db_session: Session,
    adapter: IDetailAdapter,
    force_retry_fatal: bool = False,
    ignore_sliding_window: bool = False,
    audit_ttl_days: int | None = None,
    config: IngestionRunnerConfig | None = None,
):
    """
    Orchestrates queue consumption and raw data extraction.

    Applies business rules regarding Time-To-Live (TTL) and time windows
    to select which documents should be processed. For each item,
    it requests metadata extraction from the adapter and updates the
    processing state, applying retry logic in the event of instability.

    Args:
        db_session (Session): Active SQLAlchemy session.
        adapter (IDetailAdapter): Instance of the adapter responsible for extracting details.
        force_retry_fatal (bool): If True, attempts to re-extract IDs marked as FATAL_ERROR.
        ignore_sliding_window (bool): If True, ignores time filters and scans the entire queue.
        audit_ttl_days (int | None): Time-To-Live (TTL) duration in days. Activates
            Audit Mode to reprocess completed (DONE) documents that have been inactive
            for X days, ensuring the capture of silent updates at the source.
        config (IngestionRunnerConfig | None): Retry and window policy; defaults to the
            standard configuration.
    """

    config = config or IngestionRunnerConfig()

    # Time-To-Live configs
    if audit_ttl_days is not None:
        discovered_after = None
        scraped_before = datetime.now(UTC) - timedelta(days=audit_ttl_days)
        ignore_status = [ScrapeStatus.NOT_FOUND, ScrapeStatus.FATAL_ERROR]
    else:
        discovered_after = (
            None if ignore_sliding_window else (datetime.now(UTC) - timedelta(days=config.discovery_window_days))
        )
        scraped_before = (
            None if ignore_sliding_window else (datetime.now(UTC) - timedelta(days=config.scraped_ttl_days))
        )
        ignore_status = [ScrapeStatus.NOT_FOUND]
        if not force_retry_fatal:
            ignore_status.append(ScrapeStatus.FATAL_ERROR)
        if not ignore_sliding_window:
            ignore_status.append(ScrapeStatus.DONE)

    batch = repository.get_from_queue(
        db_session, discovered_after=discovered_after, scraped_before=scraped_before, ignore_status=ignore_status
    )

    total_items = len(batch)
    if total_items == 0:
        logger.info("No documents pending in the queue.")
        return

    logger.info(f"🚀 Starting extraction of {total_items} item details...")

    for index, queue in enumerate(batch, start=1):
        doc_id = queue.description_id
        logger.info(f"⏳ Processing [{index}/{total_items}] ID: {doc_id}")

        try:
            data_scraped = adapter.fetch_details(doc_id)
            repository.save_raw_data(db_session, doc_id, data_scraped)
            repository.update_queue_status(db_session, doc_id, ScrapeStatus.DONE)

        except AdapterNotFoundError as e:
            logger.error(f"Error 404: {e}")
            repository.update_queue_status(db_session, doc_id, ScrapeStatus.NOT_FOUND, error_msg=str(e))

        except AdapterNetworkError as e:
            logger.warning(f"⚠️ Instability on {doc_id}: {e}")
            if queue.retry_count >= config.max_retries:
                repository.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))
            else:
                repository.update_queue_status(
                    db_session, doc_id, ScrapeStatus.NETWORK_ERROR, error_msg=str(e), increment_retry=True
                )

        except (AdapterFatalError, Exception) as e:
            logger.exception(f"💥 Fatal error (Parsing/DB) on {doc_id}: {e}")
            repository.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))


if __name__ == "__main__":
    from domains.ingestion.adapters.pmc_scraper import PMCScraperAdapter

    with get_db() as db:
        adapter = PMCScraperAdapter(delay_requests=0.5)

        # run_discovery_job(db, adapter=adapter)
        run_detail_scraping_job(db, adapter=adapter, ignore_sliding_window=True)
