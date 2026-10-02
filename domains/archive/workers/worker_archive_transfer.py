from sqlalchemy.orm import Session

from core.database import get_db
from core.logger import logger
from core.unit_of_work import UnitOfWork
from domains.archive.models import ArchiveReviewStatus
from domains.archive.ports.staging_source import StagingRecordSource
from domains.archive.repository import DocumentRepository, TagRepository
from domains.archive.repository.staging_source import SqlStagingRecordSource
from domains.archive.schemas.command_schema import TagLinkCommand
from domains.archive.schemas.document_schema import ArchiveDocumentDTO
from domains.archive.services.tag_service import TagService

# Batch size for the Batch Commit
BATCH_SIZE = 500


def execute(
    db_session: Session,
    source: StagingRecordSource | None = None,
) -> None:
    """
    Orchestrator responsible for copying the structured data from the Staging layer
    and initializing the records in the fact table of the Archive layer.

    The staging records arrive through the ``StagingRecordSource`` port, so this
    use case never touches the staging ORM directly.
    """
    logger.info("🚀 Starting the migration from Staging to Archive")

    source = source or SqlStagingRecordSource(db_session)

    # Instantiates the Repositories and Service
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    tag_service = TagService(tag_repo, doc_repo)
    uow = UnitOfWork(db_session)

    documents_staging = source.stream(BATCH_SIZE)

    success_count = 0
    failures = 0

    # OPTIMIZATION BUFFER: Accumulates the N:N links to insert them all at once
    batch_links = []

    for doc_staging in documents_staging:
        try:
            # 1. Builds the DTO with the raw metadata (no AI yet)
            doc_dto = ArchiveDocumentDTO(
                description_id=doc_staging.description_id,
                original_title=doc_staging.title,
                document_date=doc_staging.document_date,
                summary=doc_staging.scope_content,
                staging_content_hash=doc_staging.raw_content_hash,
                original_thumbnail_url=doc_staging.thumb_down_link,
                storage_thumbnail_uri=None,
                reference_code=doc_staging.reference_code,
                level=doc_staging.level,
                producers=doc_staging.producers,
                admin_bio_history=doc_staging.admin_bio_history,
                admin_archival_history=doc_staging.admin_archival_history,
                provenance=doc_staging.provenance,
                scope_content=doc_staging.scope_content,
                language_name=doc_staging.language_name,
                archivist_notes=doc_staging.archivist_notes,
                final_title=None,
                semantic_search_vector=None,
                anomaly_reasons=None,
                review_status=ArchiveReviewStatus.PENDING_AI,
                execution_log={},
            )

            # 2. Persists into the Fact table (ArchiveDocuments)
            with db_session.begin_nested():
                was_saved = doc_repo.upsert_archive_document(doc_dto)

            if was_saved:
                # 3. Extracts and sanitizes the old tags via the Domain Service
                tags_dtos = tag_service.extract_and_clean_tags(doc_staging.indexing_points)
                tag_ids = tag_service.process_worker_tags(tags_dtos)

                if tag_ids:
                    batch_links.extend(
                        TagLinkCommand(description_id=doc_dto.description_id, tag_id=t_id) for t_id in tag_ids
                    )

                success_count += 1

                if success_count > 0 and success_count % BATCH_SIZE == 0:
                    if batch_links:
                        tag_repo.bulk_link_tags(batch_links)
                        batch_links.clear()

                    uow.commit()
                    logger.info(f"⏳ Progress: {success_count} documents transferred to Archive...")

        except Exception as e:
            logger.error(f"❌ Error transferring document {doc_staging.description_id}: {e}")
            failures += 1
            continue

    try:
        if batch_links:
            tag_repo.bulk_link_tags(batch_links)
        uow.commit()
        logger.success(f"✅ Transfer completed! Successes: {success_count} | Failures: {failures}")
    except Exception as e:
        uow.rollback()
        logger.critical(f"🔥 Critical error in the final transfer commit: {e}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db)
