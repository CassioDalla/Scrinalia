import argparse
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from scrinalia.core.cli import non_negative_int, positive_int
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.runner_config import IngestionRunnerConfig
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.ingestion import repository
from scrinalia.domains.ingestion.models import ScrapeStatus
from scrinalia.domains.ingestion.ports import (
    AdapterFatalError,
    AdapterNetworkError,
    AdapterNotFoundError,
    IDetailAdapter,
    IDiscoveryAdapter,
)


def run_discovery_job(db_session: Session, adapter: IDiscoveryAdapter, max_pages: int | None = None) -> int:
    """
    Orchestrates the Ingestion discovery phase, retrieving new IDs from the data source.

    Uses a discovery adapter (IDiscoveryAdapter) to iterate over the
    source (web pages, spreadsheets, APIs) and inserts new identifiers
    into the Processing Queue in batches (bulk insert).

    Args:
        db_session (Session): Active SQLAlchemy session.
        adapter (IDiscoveryAdapter): Instance of the adapter responsible for retrieving IDs.
        max_pages (int | None, optional): Limit on the number of iterations/pages to process.

    Returns:
        int: How many new identifiers this run enqueued, so a caller chaining the two phases can
            report it without re-counting the queue.
    """

    logger.info("🚀 Starting ID discovery job...")

    uow = UnitOfWork(db_session)
    total_inserted = 0
    for batch_ids in adapter.fetch_new_ids(max_pages=max_pages):
        inserted_count = repository.add_in_bulk(db_session, batch_ids)
        uow.commit()
        total_inserted += inserted_count

        if inserted_count > 0:
            logger.success(f"🔥 +{inserted_count} new documents in the queue.")

    if total_inserted == 0:
        logger.warning("No new IDs were found in this execution.")

    return total_inserted


def run_detail_scraping_job(
    db_session: Session,
    adapter: IDetailAdapter,
    force_retry_fatal: bool = False,
    ignore_sliding_window: bool = False,
    audit_ttl_days: int | None = None,
    limit: int | None = None,
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
        limit (int | None): Maximum number of queue rows this run may take. ``None`` takes the whole
            pending queue, which is what one run used to do unconditionally; a bounded run leaves
            the rest pending and the next one takes the next batch, because the policy orders by
            ``last_scraped_at`` and every outcome stamps it. The one exception is a row whose *save*
            rolls back: it keeps its place at the front and holds a slot of every run until its
            write succeeds, which is the accepted limit of the bound.
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
        db_session,
        discovered_after=discovered_after,
        scraped_before=scraped_before,
        ignore_status=ignore_status,
        limit=limit,
    )

    total_items = len(batch)
    if total_items == 0:
        logger.info("No documents pending in the queue.")
        return

    logger.info(f"🚀 Starting extraction of {total_items} item details...")

    uow = UnitOfWork(db_session)
    failures = 0

    for index, queue in enumerate(batch, start=1):
        doc_id = queue.description_id
        logger.info(f"⏳ Processing [{index}/{total_items}] ID: {doc_id}")

        try:
            data_scraped = adapter.fetch_details(doc_id)

        except AdapterNotFoundError as e:
            logger.error(f"Error 404: {e}")
            failures += 1
            repository.update_queue_status(db_session, doc_id, ScrapeStatus.NOT_FOUND, error_msg=str(e))

        except AdapterNetworkError as e:
            logger.warning(f"⚠️ Instability on {doc_id}: {e}")
            failures += 1
            if queue.retry_count >= config.max_retries:
                repository.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))
            else:
                repository.update_queue_status(
                    db_session, doc_id, ScrapeStatus.NETWORK_ERROR, error_msg=str(e), increment_retry=True
                )

        except (AdapterFatalError, Exception) as e:
            logger.exception(f"💥 Fatal error (Parsing/DB) on {doc_id}: {e}")
            failures += 1
            repository.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))

        else:
            # The raw payload and the queue status must land in the same transaction.
            try:
                repository.save_raw_data(db_session, doc_id, data_scraped)
                repository.update_queue_status(db_session, doc_id, ScrapeStatus.DONE)
            except Exception as e:
                logger.exception(f"💥 Database error persisting {doc_id}: {e}")
                failures += 1
                uow.rollback()
                continue

        try:
            uow.commit()
        except Exception as e:
            logger.error(f"💥 Failed to persist the result of {doc_id}: {e}")
            failures += 1
            uow.rollback()

    remaining = repository.count_pending(
        db_session,
        ignore_status=ignore_status,
        discovered_after=discovered_after,
        scraped_before=scraped_before,
    )
    logger.info(f"🎯 Extraction finished. taken: {total_items} | failures: {failures} | still pending: {remaining}")


def config_from_args(args: argparse.Namespace) -> IngestionRunnerConfig:
    """
    The run policy, with only the fields the command line actually set.

    The defaults stay in :class:`IngestionRunnerConfig` and are not restated here: an option left
    out keeps following the code, so changing a window in the dataclass changes every run that did
    not name it, instead of being shadowed by a second copy of the number in the parser.
    """
    overrides = {
        "max_retries": args.max_retries,
        "discovery_window_days": args.discovery_window_days,
        "scraped_ttl_days": args.scraped_ttl_days,
    }
    return replace(IngestionRunnerConfig(), **{key: value for key, value in overrides.items() if value is not None})


def _add_scrape_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=positive_int, default=None, help="Maximum queue rows this run may take.")
    parser.add_argument(
        "--audit-ttl-days",
        type=positive_int,
        default=None,
        help="Re-read the DONE rows last scraped more than N days ago (audit mode).",
    )
    parser.add_argument("--force-retry-fatal", action="store_true", help="Also take the rows marked FATAL_ERROR.")
    parser.add_argument(
        "--ignore-sliding-window",
        action="store_true",
        help="Ignore the discovery/TTL windows and take every row the statuses allow.",
    )
    parser.add_argument("--max-retries", type=non_negative_int, default=None, help="Transient failures before FATAL.")
    parser.add_argument(
        "--discovery-window-days", type=positive_int, default=None, help="Only rows discovered in the last N days."
    )
    parser.add_argument(
        "--scraped-ttl-days", type=positive_int, default=None, help="Only rows last scraped more than N days ago."
    )


def _build_parser() -> argparse.ArgumentParser:
    """
    The host CLI: the two phases of the ingestion and, in ``run``, both in one process.

    The verbs are the domain's two ports (``IDiscoveryAdapter``/``IDetailAdapter``) and not one
    site's vocabulary, so a second origin is a registry entry and another ``--origin``, not another
    command. It deliberately lives on ``__main__`` and not in the operations runner: the runner
    carries the archive workers' ledger and preset resolution, and the scrape is a host operation
    with no engine to configure (the operations panel surfacing it is its own change).
    """
    origin = argparse.ArgumentParser(add_help=False)
    origin.add_argument("--origin", default=None, help="Origin code; ACERVO_SOURCE when omitted.")

    parser = argparse.ArgumentParser(
        prog="python -m scrinalia.domains.ingestion.worker",
        description="Reads one origin into the raw layer: its identifier listing and each detail page.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    discover = commands.add_parser(
        "discover", parents=[origin], help="Lists the origin's identifiers and enqueues the new ones."
    )
    discover.add_argument("--pages", type=positive_int, default=None, help="How many listing pages to walk.")

    scrape = commands.add_parser(
        "scrape", parents=[origin], help="Fetches the detail page of each identifier the queue holds."
    )
    _add_scrape_flags(scrape)

    run = commands.add_parser("run", parents=[origin], help="Discovery followed by the scrape, in one process.")
    run.add_argument("--pages", type=positive_int, default=None, help="How many listing pages to walk.")
    _add_scrape_flags(run)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Runs one phase (or both) against the selected origin; returns the process exit code."""
    args = _build_parser().parse_args(argv)

    # Imported here, not at module level: the registry drags in the adapter module (requests, bs4)
    # and this module is imported by processes that never scrape.
    from scrinalia.domains.ingestion.sources import get_adapters

    try:
        adapters = get_adapters(args.origin)
        discovery = adapters.require_discovery() if args.command in ("discover", "run") else None
        detail = adapters.require_detail() if args.command in ("scrape", "run") else None
    except ValueError as error:
        logger.error(f"❌ {error}")
        return 1

    with get_db() as db:
        if discovery is not None:
            run_discovery_job(db, adapter=discovery, max_pages=args.pages)
        if detail is not None:
            run_detail_scraping_job(
                db,
                adapter=detail,
                force_retry_fatal=args.force_retry_fatal,
                ignore_sliding_window=args.ignore_sliding_window,
                audit_ttl_days=args.audit_ttl_days,
                limit=args.limit,
                config=config_from_args(args),
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
