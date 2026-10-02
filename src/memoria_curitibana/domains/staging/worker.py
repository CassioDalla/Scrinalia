from pydantic import ValidationError
from sqlalchemy.orm import Session

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.core.unit_of_work import UnitOfWork
from memoria_curitibana.domains.staging.ports import RawRecordSource, StagingDocumentWriter
from memoria_curitibana.domains.staging.repository import SqlRawRecordSource, SqlStagingDocumentWriter
from memoria_curitibana.domains.staging.schemas import StagingDocumentDTO


def run_staging_pipeline(
    db_session: Session,
    source: RawRecordSource | None = None,
    writer: StagingDocumentWriter | None = None,
    uow: UnitOfWork | None = None,
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
        source (RawRecordSource | None): Input port; defaults to the SQL adapter.
        writer (StagingDocumentWriter | None): Output port; defaults to the SQL adapter.
    """

    source = source or SqlRawRecordSource(db_session)
    writer = writer or SqlStagingDocumentWriter(db_session)
    uow = uow or UnitOfWork(db_session)

    logger.info("🔍 Checking pending documents at the Ingestion Domain...")
    pending_records = source.next_batch()

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
            # Validation and Cleaning (Pydantic)
            clean_record = StagingDocumentDTO.model_validate(
                {
                    "description_id": raw_record.description_id,
                    "content_hash": raw_record.content_hash,
                    "payload": raw_record.payload,
                    "raw_title": raw_record.raw_title,
                }
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
        logger.info(f"🎯 Staging Pipeline Completed! Success: {success} | failures: {failures}")
    except Exception as e:
        uow.rollback()
        logger.critical(f"🔥 Critical error during final commit:{e!s}")


if __name__ == "__main__":
    with get_db() as db:
        run_staging_pipeline(db)
