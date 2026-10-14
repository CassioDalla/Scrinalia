import argparse

from pydantic import ValidationError
from sqlalchemy.orm import Session

from scrinalia.core.cli import positive_int
from scrinalia.core.database import get_db
from scrinalia.core.logger import logger
from scrinalia.core.unit_of_work import UnitOfWork
from scrinalia.domains.ingestion.ports import SourceSchema
from scrinalia.domains.staging.ports import RawRecordSource, StagingDocumentWriter
from scrinalia.domains.staging.repository import SqlRawRecordSource, SqlStagingDocumentWriter
from scrinalia.domains.staging.schemas import SOURCE_SCHEMA_CONTEXT_KEY, StagingDocumentDTO


def run_staging_pipeline(
    db_session: Session,
    source_schema: SourceSchema | None = None,
    source: RawRecordSource | None = None,
    writer: StagingDocumentWriter | None = None,
    uow: UnitOfWork | None = None,
    force: bool = False,
    limit: int | None = None,
    after: str | None = None,
) -> None:
    """
    Orchestrates the transformation pipeline (Transform/Load) for the Staging layer.

    Executes the following atomic steps:
    1. Fetches pending or outdated raw documents through the ``RawRecordSource`` port.
    2. Validates, sanitizes, and casts data types using the Pydantic schema.
    3. Persists through the ``StagingDocumentWriter`` port.
    4. Applies savepoints (begin_nested) to ensure faulty documents
    are skipped without aborting the entire batch transaction.

    The ports default to their PostgreSQL adapters, but can be overridden (tests,
    alternate sources) without the use case knowing about the ingestion ORM.

    Args:
        db_session (Session): Active SQLAlchemy session.
        source_schema (SourceSchema | None): The origin's field vocabulary. Defaults to the one
            ``ACERVO_SOURCE`` names; there is no built-in fallback, so a deployment that never
            declared its origin fails here instead of filing every column as unknown.
        source (RawRecordSource | None): Input port; defaults to the SQL adapter.
        writer (StagingDocumentWriter | None): Output port; defaults to the SQL adapter.
        force (bool): Re-parses every raw record instead of only the changed ones. Required
            after a parser change, because the source payload hash did not change.
        limit (int | None): Maximum raw records this run may take. ``None`` is the whole pending
            set, which is what one transform used to do unconditionally; a bounded run leaves the
            rest for the next one and reports how many, so a 100-document scrape does not force a
            full-collection transform.
        after (str | None): Keyset cursor over ``description_id``, the way a bounded ``force`` run
            resumes: the CDC advances on its own, a forced re-parse does not.
    """
    # Imported here, not at module level: the staging worker is a step of the pipeline, and the
    # origin registry drags in the adapter module (requests, bs4) that this process never uses.
    from scrinalia.domains.ingestion.sources import get_source_schema

    source_schema = source_schema or get_source_schema()
    source = source or SqlRawRecordSource(db_session)
    writer = writer or SqlStagingDocumentWriter(db_session)
    uow = uow or UnitOfWork(db_session)

    logger.info("🔍 Checking pending documents at the Ingestion Domain...")
    pending_records = source.next_batch(force=force, limit=limit, after=after)

    total = len(pending_records)
    if total == 0:
        logger.success("✅ No new or modified documents found.")
        return

    logger.info(f"🚀 Starting processing of {total} documents...")

    success = 0
    failures = 0

    for i, raw_record in enumerate(pending_records, start=1):
        doc_id = raw_record.description_id
        try:
            # Validation and Cleaning (Pydantic), with the origin's vocabulary as context.
            clean_record = StagingDocumentDTO.model_validate(
                {
                    "description_id": raw_record.description_id,
                    "content_hash": raw_record.content_hash,
                    "payload": raw_record.payload,
                    "raw_title": raw_record.raw_title,
                },
                context={SOURCE_SCHEMA_CONTEXT_KEY: source_schema},
            )

            # Persistency
            with db_session.begin_nested():
                writer.save(clean_record)

            success += 1
            if i % 50 == 0:
                logger.info(f"⏳ Processed: {i}/{total}...")

        except ValidationError as e:
            failures += 1
            logger.error(f"❌Pydantic rejected doc {doc_id}: {e.error_count()} errors found.")
            logger.debug(f"Pydantic error details: {e.errors()}")

        except Exception as e:
            failures += 1
            logger.error(f"💥 Fatal error saving document {doc_id} to the database: {e!s}")
            continue

    try:
        uow.commit()
    except Exception as e:
        uow.rollback()
        logger.critical(f"🔥 Critical error during final commit:{e!s}")
        return

    remaining = source.count_pending(force=force, after=after)
    logger.info(
        f"🎯 Staging Pipeline Completed! Success: {success} | failures: {failures} | still pending: {remaining}"
    )

    # The cursor is the one thing a bounded forced run cannot derive from the CDC, and without
    # naming it the operator of a batched re-parse has no way to ask for the next window. The batch
    # is ordered by ``description_id``, so its last record is where the next one opens.
    if force and limit is not None:
        logger.info(
            f"↩️ Forced window ended at {pending_records[-1].description_id}: "
            f"resume with --force --limit {limit} --after {pending_records[-1].description_id}"
        )


def _build_parser() -> argparse.ArgumentParser:
    """
    The host CLI of the transform.

    ``--force`` is the parser-change escape hatch the CDC cannot provide, and ``--after`` is what
    keeps a forced re-parse bounded: the hash comparison advances a limited run by itself, but a
    forced one re-reads the same window every time unless it is told where to resume.
    """
    parser = argparse.ArgumentParser(
        prog="python -m scrinalia.domains.staging.worker",
        description="Transforms the raw records into structured staging documents.",
    )
    parser.add_argument("--force", action="store_true", help="Re-parses every raw record, ignoring the CDC.")
    parser.add_argument("--limit", type=positive_int, default=None, help="Maximum raw records this run may take.")
    parser.add_argument(
        "--after",
        default=None,
        help="Resume a forced re-parse at the first description_id greater than this.",
    )
    parser.add_argument("--origin", default=None, help="Origin code; ACERVO_SOURCE when omitted.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Runs one bounded transform; returns the process exit code."""
    # Imported here, not at module level, for the same reason the pipeline imports it: this module
    # is imported by the API process, which never reads an origin.
    from scrinalia.domains.ingestion.sources import get_source_schema

    args = _build_parser().parse_args(argv)

    try:
        source_schema = get_source_schema(args.origin)
    except ValueError as error:
        logger.error(f"❌ {error}")
        return 1

    with get_db() as db:
        run_staging_pipeline(
            db,
            source_schema=source_schema,
            force=args.force,
            limit=args.limit,
            after=args.after,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
