from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.database import get_db
from core.logger import logger
from domains.staging import repository
from domains.staging.schemas import StagingDocumentDTO


def run_staging_pipeline(db_session: Session) -> None:
    """
    Orchestrates the transformation pipeline (Transform/Load) for the Staging layer.

    Executes the following atomic steps:
    1. Fetches pending or outdated raw documents (RawData).
    2. Validates, sanitizes, and casts data types using the Pydantic schema.
    3. Updates the structured relational database using repository upserts.
    4. Applies savepoints (begin_nested) to ensure faulty documents
    are skipped without aborting the entire batch transaction.

    Args:
        db_session (Session): Active SQLAlchemy session.
    """

    logger.info("🔍 Checking pending documents at the Ingestion Domain...")
    pending_records = repository.get_pending_raw_records(db_session)

    total = len(pending_records)
    if total == 0:
        logger.success("✅ No new or modified documents found.")
        return

    logger.info(f"🚀 Starting processing of {total} documents...")

    success = 0
    failures = 0

    for i, raw_data in enumerate(pending_records, start=1):
        doc_id = raw_data.get("description_id", "UNKNOWN")
        try:
            # Validation and Cleaning (Pydantic)
            clean_record = StagingDocumentDTO.model_validate(raw_data)

            # Persistency
            with db_session.begin_nested():
                repository.upsert_staging_document(db_session, clean_record)

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
        db_session.commit()
        logger.info(f"🎯 Staging Pipeline Completed! Success: {success} | failures: {failures}")
    except Exception as e:
        db_session.rollback()
        logger.critical(f"🔥 Critical error during final commit:{e!s}")


if __name__ == "__main__":
    with get_db() as db:
        run_staging_pipeline(db)
