from typing import Any

from sqlalchemy.orm import Session

from memoria_curitibana.core.database import get_db
from memoria_curitibana.core.logger import logger
from memoria_curitibana.core.unit_of_work import UnitOfWork
from memoria_curitibana.domains.archive.domain.hierarchy import build_path
from memoria_curitibana.domains.archive.domain.hierarchy_code import normalize_reference_code
from memoria_curitibana.domains.archive.domain.level_catalog import resolve_level_id
from memoria_curitibana.domains.archive.models import ArchiveReviewStatus
from memoria_curitibana.domains.archive.ports.staging_source import StagingRecordSource
from memoria_curitibana.domains.archive.repository import DocumentRepository, TagRepository
from memoria_curitibana.domains.archive.repository.level_catalog_repo import LevelCatalogRepository
from memoria_curitibana.domains.archive.repository.staging_source import SqlStagingRecordSource
from memoria_curitibana.domains.archive.schemas.command_schema import TagLinkCommand
from memoria_curitibana.domains.archive.schemas.document_schema import ArchiveDocumentDTO
from memoria_curitibana.domains.archive.services.tag_service import TagService
from memoria_curitibana.domains.archive.worker_stamp import (
    HIERARCHY_PARENT,
    HIERARCHY_PARENT_PENDING,
    HIERARCHY_PARENT_RESOLVED,
)

# Batch size for the Batch Commit
BATCH_SIZE = 500

#: Separators an origin may use to spell the full path of codes (``"BR PRADAP / SMU / ED"``). Used
#: only as a fallback: the parent *code* is what resolution reads when it is present, because a
#: path is a snapshot of the arrangement and a code is the thing itself.
_PATH_SEPARATORS = ("/", ">", "|", "\\")


def _declared_parent_code(record) -> str | None:
    """
    The parent the origin declared, from the parent code or, failing that, from the full path.

    ``hierarchy_path`` is the fallback for an origin that knows the whole chain but not the link:
    the penultimate segment is the parent by construction.
    """
    if record.parent_reference_code:
        return normalize_reference_code(record.parent_reference_code)
    raw_path = record.hierarchy_path
    if not raw_path:
        return None
    for separator in _PATH_SEPARATORS:
        raw_path = raw_path.replace(separator, "\x00")
    segments = [segment.strip() for segment in raw_path.split("\x00") if segment.strip()]
    return normalize_reference_code(segments[-2]) if len(segments) >= 2 else None


def _resolve_pending_parents(db_session: Session, doc_repo: DocumentRepository) -> int:
    """
    Retries the declared parents that had not arrived when their child was loaded.

    The origin is allowed to deliver a child before its parent, and the transfer must not fail for
    it — but "orphan and marked" is only honest if something ever comes back for it. This is that
    something, and it runs at the end of every transfer, so a parent that arrives in a later batch
    links the children that were already waiting.
    """
    pending = doc_repo.list_pending_hierarchy_parents()
    linked = 0
    for description_id, parent_code in pending:
        parent = doc_repo.find_by_reference_code(parent_code)
        if parent is None:
            continue
        doc_repo.resolve_hierarchy_parent(description_id, parent.description_id, parent.path)
        linked += 1
    return linked


def execute(
    db_session: Session,
    source: StagingRecordSource | None = None,
) -> None:
    """
    Orchestrator responsible for copying the structured data from the Staging layer
    and initializing the records in the fact table of the Archive layer.

    The staging records arrive through the ``StagingRecordSource`` port, so this
    use case never touches the staging ORM directly.

    The declared level arrives as text and is resolved against the catalogue here. An unknown
    spelling leaves the description **unclassified** instead of failing the load: the source is
    allowed to be ahead of the catalogue, and the diagnostics report what never matched. The
    arrangement itself is not read from the source yet (that is H6), so every migrated description
    enters as a root: its path is its own id.
    """
    logger.info("🚀 Starting the migration from Staging to Archive")

    source = source or SqlStagingRecordSource(db_session)

    # Instantiates the Repositories and Service
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    tag_service = TagService(tag_repo, doc_repo)
    level_repo = LevelCatalogRepository(db_session)
    level_index = level_repo.level_index()
    uow = UnitOfWork(db_session)

    documents_staging = source.stream(BATCH_SIZE)

    success_count = 0
    failures = 0
    unknown_levels = 0
    declared_parents = 0
    orphans_pending = 0

    #: ``normalized parent code -> (description_id, path)`` of the parent, or ``(None, None)`` when
    #: the collection has no such record yet. Cached per run because the vocabulary of an origin is
    #: tiny (the third token of the real codes has eight values) and the lookup is a folded scan.
    parent_cache: dict[str, tuple[str | None, str | None]] = {}

    # OPTIMIZATION BUFFER: Accumulates the N:N links to insert them all at once
    batch_links = []

    for doc_staging in documents_staging:
        try:
            # 1. Builds the DTO with the raw metadata (no AI yet)
            level_id = resolve_level_id(level_index, doc_staging.level)
            if doc_staging.level and level_id is None:
                unknown_levels += 1
                logger.warning(f"⚠️ Unknown description level '{doc_staging.level}' on {doc_staging.description_id}")

            # The arrangement is only spoken about when the origin speaks about it. Omitting the
            # fields lets the upsert leave whatever curation placed exactly where it is.
            # Typed ``Any`` on purpose: the keys are the DTO's, and the whole point is to omit
            # them entirely when the origin declared nothing.
            hierarchy_fields: dict[str, Any] = {}
            execution_log: dict[str, str] = {}
            parent_code = _declared_parent_code(doc_staging)
            if parent_code:
                declared_parents += 1
                if parent_code not in parent_cache:
                    parent = doc_repo.find_by_reference_code(parent_code)
                    parent_cache[parent_code] = (parent.description_id, parent.path) if parent else (None, None)
                parent_id, parent_path = parent_cache[parent_code]
                hierarchy_fields = {
                    "parent_id": parent_id,
                    "path": build_path(parent_path, doc_staging.description_id),
                }
                if parent_id is None:
                    # The parent has not arrived. The child is loaded as a root and *marked*, so the
                    # retry at the end of the run (or of a later one) can link it.
                    orphans_pending += 1
                    execution_log = HIERARCHY_PARENT.mark_value({}, f"{HIERARCHY_PARENT_PENDING}{parent_code}")
                else:
                    execution_log = HIERARCHY_PARENT.mark_value({}, f"{HIERARCHY_PARENT_RESOLVED}{parent_id}")

            doc_dto = ArchiveDocumentDTO(
                description_id=doc_staging.description_id,
                original_title=doc_staging.title,
                document_date=doc_staging.document_date,
                summary=doc_staging.scope_content,
                # Parsed content, not the raw payload: a parser fix must reach the archive.
                staging_content_hash=doc_staging.parsed_content_hash(),
                original_thumbnail_url=doc_staging.thumb_down_link,
                storage_thumbnail_uri=None,
                reference_code=doc_staging.reference_code,
                level_id=level_id,
                producers=doc_staging.producers,
                admin_bio_history=doc_staging.admin_bio_history,
                admin_archival_history=doc_staging.admin_archival_history,
                provenance=doc_staging.provenance,
                scope_content=doc_staging.scope_content,
                language_name=doc_staging.language_name,
                archivist_notes=doc_staging.archivist_notes,
                final_title=None,
                anomaly_reasons=None,
                review_status=ArchiveReviewStatus.PENDING_AI,
                execution_log=execution_log,
                **hierarchy_fields,
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

        # Second chance for the children whose parent had not arrived when they were loaded.
        linked = _resolve_pending_parents(db_session, doc_repo)
        uow.commit()

        logger.success(
            f"✅ Transfer completed! Successes: {success_count} | Failures: {failures} | "
            f"Unclassified levels: {unknown_levels} | Declared parents: {declared_parents} | "
            f"Orphans waiting for a parent: {orphans_pending} | Parent links resolved late: {linked}"
        )
    except Exception as e:
        uow.rollback()
        logger.critical(f"🔥 Critical error in the final transfer commit: {e}")


if __name__ == "__main__":
    with get_db() as db:
        execute(db)
