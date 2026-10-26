import argparse
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from scrinalia.core.cli import non_negative_int, positive_int
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.runner_config import IngestionRunnerConfig
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.ingestion import repository
from scrinalia.domains.ingestion.exceptions import InvalidOriginConfigError, OriginNotFoundError
from scrinalia.domains.ingestion.models import ScrapeStatus
from scrinalia.domains.ingestion.ports import (
    AdapterFatalError,
    AdapterNetworkError,
    AdapterNotFoundError,
    IDetailAdapter,
    IDiscoveryAdapter,
)
from scrinalia.domains.staging.repository import SqlRawRecordSource
from scrinalia.domains.staging.worker import run_staging_pipeline


def run_discovery_job(
    db_session: Session,
    adapter: IDiscoveryAdapter,
    max_pages: int | None = None,
    *,
    origin_code: str | None = None,
    run_control: Any | None = None,
) -> int:
    """
    Orchestrates the Ingestion discovery phase, retrieving new IDs from the data source.

    Uses a discovery adapter (IDiscoveryAdapter) to iterate over the
    source (web pages, spreadsheets, APIs) and inserts new identifiers
    into the Processing Queue in batches (bulk insert).

    Args:
        db_session (Session): Active SQLAlchemy session.
        adapter (IDiscoveryAdapter): Instance of the adapter responsible for retrieving IDs.
        max_pages (int | None, optional): Limit on the number of iterations/pages to process.
        origin_code (str | None): The origin whose queue receives the ids.
        run_control (Any | None): The cancellation control, checked once per page batch.

    Returns:
        int: How many new identifiers this run enqueued, so a caller chaining the two phases can
            report it without re-counting the queue.
    """

    logger.info("🚀 Starting ID discovery job...")

    uow = UnitOfWork(db_session)
    total_inserted = 0
    for batch_ids in adapter.fetch_new_ids(max_pages=max_pages):
        if run_control is not None:
            run_control.checkpoint()
        inserted_count = repository.add_in_bulk(db_session, batch_ids, origin_code=origin_code)
        uow.commit()
        total_inserted += inserted_count

        if inserted_count > 0:
            logger.success(f"🔥 +{inserted_count} new documents in the queue.")

    if total_inserted == 0:
        logger.warning("No new IDs were found in this execution.")

    return total_inserted


def queue_window(
    config: IngestionRunnerConfig,
    *,
    audit_ttl_days: int | None = None,
    ignore_sliding_window: bool = False,
    force_retry_fatal: bool = False,
) -> tuple[datetime | None, datetime | None, list[ScrapeStatus]]:
    """
    The sliding-window policy of one run, as the three values the queue predicate reads.

    It belongs to one function because the run and the panel's counter must apply the same policy:
    a number computed by a second copy of this block would answer a different question from the one
    the next execution asks. The order is the ADR 0014 order — audit mode overrides the window,
    then the discovery/TTL filters, then the statuses the policy excludes.
    """
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
    return discovered_after, scraped_before, ignore_status


def run_detail_scraping_job(
    db_session: Session,
    adapter: IDetailAdapter,
    force_retry_fatal: bool = False,
    ignore_sliding_window: bool = False,
    audit_ttl_days: int | None = None,
    limit: int | None = None,
    config: IngestionRunnerConfig | None = None,
    origin_code: str | None = None,
    run_control: Any | None = None,
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
        origin_code (str | None): The origin whose queue this run consumes. ``None`` is the whole
            queue, which is what the host command still does; a worker run always names one.
        run_control (Any | None): The cancellation control, checked once per queue row.
    """

    config = config or IngestionRunnerConfig()
    discovered_after, scraped_before, ignore_status = queue_window(
        config,
        audit_ttl_days=audit_ttl_days,
        ignore_sliding_window=ignore_sliding_window,
        force_retry_fatal=force_retry_fatal,
    )

    batch = repository.get_from_queue(
        db_session,
        discovered_after=discovered_after,
        scraped_before=scraped_before,
        ignore_status=ignore_status,
        limit=limit,
        origin_code=origin_code,
    )

    total_items = len(batch)
    if total_items == 0:
        logger.info("No documents pending in the queue.")
        return

    logger.info(f"🚀 Starting extraction of {total_items} item details...")

    uow = UnitOfWork(db_session)
    failures = 0

    for index, queue in enumerate(batch, start=1):
        if run_control is not None:
            run_control.checkpoint()
        doc_id = queue.description_id
        logger.info(f"⏳ Processing [{index}/{total_items}] ID: {doc_id}")

        try:
            data_scraped = adapter.fetch_details(doc_id)

        except AdapterNotFoundError as e:
            logger.error(f"Error 404: {e}")
            failures += 1
            repository.update_queue_status(
                db_session, doc_id, ScrapeStatus.NOT_FOUND, error_msg=str(e), origin_code=origin_code
            )

        except AdapterNetworkError as e:
            logger.warning(f"⚠️ Instability on {doc_id}: {e}")
            failures += 1
            if queue.retry_count >= config.max_retries:
                repository.update_queue_status(
                    db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e), origin_code=origin_code
                )
            else:
                repository.update_queue_status(
                    db_session,
                    doc_id,
                    ScrapeStatus.NETWORK_ERROR,
                    error_msg=str(e),
                    increment_retry=True,
                    origin_code=origin_code,
                )

        except (AdapterFatalError, Exception) as e:
            logger.exception(f"💥 Fatal error (Parsing/DB) on {doc_id}: {e}")
            failures += 1
            repository.update_queue_status(
                db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e), origin_code=origin_code
            )

        else:
            # The raw payload and the queue status must land in the same transaction.
            try:
                repository.save_raw_data(db_session, doc_id, data_scraped, origin_code=origin_code)
                repository.update_queue_status(db_session, doc_id, ScrapeStatus.DONE, origin_code=origin_code)
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
        origin_code=origin_code,
    )
    logger.info(f"🎯 Extraction finished. taken: {total_items} | failures: {failures} | still pending: {remaining}")


def _config_from_options(
    *,
    max_retries: int | None = None,
    discovery_window_days: int | None = None,
    scraped_ttl_days: int | None = None,
) -> IngestionRunnerConfig:
    """The run policy with only the fields the caller set; the defaults stay in the dataclass."""
    overrides = {
        "max_retries": max_retries,
        "discovery_window_days": discovery_window_days,
        "scraped_ttl_days": scraped_ttl_days,
    }
    return replace(IngestionRunnerConfig(), **{key: value for key, value in overrides.items() if value is not None})


def execute(
    db_session: Session,
    origin_code: str,
    pages: int | None = 1,
    limit: int | None = None,
    audit_ttl_days: int | None = None,
    force_retry_fatal: bool = False,
    ignore_sliding_window: bool = False,
    max_retries: int | None = None,
    discovery_window_days: int | None = None,
    scraped_ttl_days: int | None = None,
    run_control: Any | None = None,
) -> None:
    """
    One ingestion execution: discovery (when the origin has it), detail extraction, then staging.

    It is the worker body the runner calls, and the same three steps the host ``run`` command does,
    with two differences that matter: the origin is a row (and an explicit code), and every phase is
    bounded by the run's options. The manual origin skips straight to staging, because its raw
    record is the form itself.

    The staging step is what makes the run *end to end*: a scrape that leaves the raw payload in the
    bucket and never structures it would be a queue with no consumer. The archive transfer remains
    the next stage of the panel, a worker of its own.

    The form-based origins (``manual`` and ``csv``) skip straight to staging, because their raw
    record is the input the person sent; a run of one of them only retries a row an earlier import
    could not structure.
    """
    from scrinalia.domains.ingestion.origin_registry import OriginKind
    from scrinalia.domains.ingestion.origins import get_origin_definition

    definition = get_origin_definition(origin_code, db_session)
    if definition.summary.kind in (OriginKind.MANUAL, OriginKind.CSV):
        run_staging_pipeline(
            db_session,
            source_schema=definition.schema,
            origin_code=origin_code,
            limit=limit,
            run_control=run_control,
        )
        return

    config = _config_from_options(
        max_retries=max_retries,
        discovery_window_days=discovery_window_days,
        scraped_ttl_days=scraped_ttl_days,
    )

    discovery = definition.adapters.discovery
    if discovery is not None and pages != 0:
        run_discovery_job(
            db_session,
            adapter=discovery,
            max_pages=pages,
            origin_code=origin_code,
            run_control=run_control,
        )

    detail = definition.adapters.detail
    if detail is not None:
        run_detail_scraping_job(
            db_session,
            adapter=detail,
            force_retry_fatal=force_retry_fatal,
            ignore_sliding_window=ignore_sliding_window,
            audit_ttl_days=audit_ttl_days,
            limit=limit,
            config=config,
            origin_code=origin_code,
            run_control=run_control,
        )

    run_staging_pipeline(
        db_session,
        origin_code=origin_code,
        limit=limit,
        run_control=run_control,
    )


def count_pending(
    db_session: Session,
    origin_code: str | None = None,
    *,
    audit_ttl_days: int | None = None,
    force_retry_fatal: bool = False,
    ignore_sliding_window: bool = False,
    max_retries: int | None = None,
    discovery_window_days: int | None = None,
    scraped_ttl_days: int | None = None,
    **_: object,
) -> int:
    """
    What the next execution of this origin would take, through the run's own policy.

    A form-based origin's queue is the raw records not yet staged; a scraper's is the
    ``scraping_queue`` window. Both answers come from the same helpers ``execute`` uses, so the
    number the panel shows and the batch the next run takes cannot disagree.
    """
    from scrinalia.domains.ingestion.origin_registry import OriginKind, get_origin_summary

    if not origin_code:
        raise ValueError("A fila da ingestão é por origem: informe origin_code.")
    summary = get_origin_summary(origin_code)
    if summary.kind in (OriginKind.MANUAL, OriginKind.CSV):
        return SqlRawRecordSource(db_session).count_pending(origin_code=origin_code)

    config = _config_from_options(
        max_retries=max_retries,
        discovery_window_days=discovery_window_days,
        scraped_ttl_days=scraped_ttl_days,
    )
    discovered_after, scraped_before, ignore_status = queue_window(
        config,
        audit_ttl_days=audit_ttl_days,
        ignore_sliding_window=ignore_sliding_window,
        force_retry_fatal=force_retry_fatal,
    )
    return repository.count_pending(
        db_session,
        ignore_status=ignore_status,
        discovered_after=discovered_after,
        scraped_before=scraped_before,
        origin_code=origin_code,
    )


def count_processed(db_session: Session, origin_code: str | None = None, **_: object) -> int:
    """Units the origin already produced: raw payloads for the form-based origins, ``DONE`` rows otherwise."""
    from scrinalia.domains.ingestion.origin_registry import OriginKind, get_origin_summary

    if origin_code and get_origin_summary(origin_code).kind in (OriginKind.MANUAL, OriginKind.CSV):
        return repository.count_raw_data(db_session, origin_code=origin_code)
    return repository.count_processed(db_session, origin_code=origin_code)


def count_failed(db_session: Session, origin_code: str | None = None, **_: object) -> int:
    """Terminal failures of the origin's queue; a form-based origin has no scrape to fail."""
    from scrinalia.domains.ingestion.origin_registry import OriginKind, get_origin_summary

    if origin_code and get_origin_summary(origin_code).kind in (OriginKind.MANUAL, OriginKind.CSV):
        return 0
    return repository.count_failed(db_session, origin_code=origin_code)


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
    origin.add_argument("--origin", required=True, help="Origin code (see the ingestion screen).")

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

    with get_db() as db:
        try:
            adapters = get_adapters(args.origin, db)
            discovery = adapters.require_discovery() if args.command in ("discover", "run") else None
            detail = adapters.require_detail() if args.command in ("scrape", "run") else None
        except (ValueError, OriginNotFoundError, InvalidOriginConfigError) as error:
            logger.error(f"❌ {error}")
            return 1

        if discovery is not None:
            run_discovery_job(db, adapter=discovery, max_pages=args.pages, origin_code=args.origin)
        if detail is not None:
            run_detail_scraping_job(
                db,
                adapter=detail,
                force_retry_fatal=args.force_retry_fatal,
                ignore_sliding_window=args.ignore_sliding_window,
                audit_ttl_days=args.audit_ttl_days,
                limit=args.limit,
                config=config_from_args(args),
                origin_code=args.origin,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
