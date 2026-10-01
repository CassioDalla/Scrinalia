from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from domains.ingestion.models import RawData
from domains.staging.models import StagingDocument
from domains.staging.schemas import StagingDocumentDTO


def get_pending_raw_records(db: Session) -> list[dict[str, Any]]:
    """
    Identifies raw documents awaiting transformation or reprocessing.

    Implements the Change Data Capture (CDC) pattern using Hash Tracking.
    Performs a LEFT JOIN between the newly acquired raw data (RawData) and the
    structured table (StagingDocument).

    Returns the payload only if:
        1. The document is new (does not exist in Staging).
        2. The hash of the current raw document differs from the previously processed hash
            (indicating the document has been updated at the source).

    Args:
        db (Session): Active SQLAlchemy session.

    Returns:
        list[dict[str, Any]]: A list of dictionaries containing raw data ready
        for the Pydantic parser.
    """

    stmt = (
        select(RawData.description_id, RawData.payload, RawData.content_hash, RawData.raw_title)
        .outerjoin(StagingDocument, RawData.description_id == StagingDocument.description_id)
        .where((StagingDocument.description_id.is_(None)) | (StagingDocument.raw_content_hash != RawData.content_hash))
    )

    result = db.execute(stmt)
    return [dict(row._mapping) for row in result]


def upsert_staging_document(db: Session, record: StagingDocumentDTO) -> None:
    """
    Persists a validated and structured document in the Staging layer.

    Uses a native PostgreSQL 'UPSERT' command. If the document identifier is new,
    it performs an INSERT. If it already exists (a reprocessing scenario due to
    source changes), it performs an UPDATE, replacing outdated values ​​with new
    ones extracted from the Pydantic model.

    Args:
        db (Session): Active SQLAlchemy session.
        record (StagingDocumentSchema): DTO object validated against ISAD(G) rules.
    """

    staging_dict = record.model_dump(exclude_unset=True)
    stmt = insert(StagingDocument).values(staging_dict)
    update_dict = {col.name: col for col in stmt.excluded if col.name != "description_id"}
    stmt = stmt.on_conflict_do_update(index_elements=["description_id"], set_=update_dict)

    db.execute(stmt)
