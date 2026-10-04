from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from memoria_curitibana.domains.ingestion.models import RawData
from memoria_curitibana.domains.staging.models import StagingDocument
from memoria_curitibana.domains.staging.schemas import RawRecord, StagingDocumentDTO


class SqlRawRecordSource:
    """
    Adapter implementing ``RawRecordSource`` on top of PostgreSQL.

    This is the ONLY place that knows about the ingestion ``RawData`` model: it
    performs the CDC (Change Data Capture) comparison by content hash so the
    application layer never joins across domains itself.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def next_batch(self, force: bool = False) -> list[RawRecord]:
        """Pending records by CDC, or every record when ``force`` asks for a full re-parse."""
        stmt = select(RawData.description_id, RawData.payload, RawData.content_hash, RawData.raw_title)
        if not force:
            stmt = stmt.outerjoin(StagingDocument, RawData.description_id == StagingDocument.description_id).where(
                (StagingDocument.description_id.is_(None)) | (StagingDocument.raw_content_hash != RawData.content_hash)
            )
        return [RawRecord.model_validate(row._mapping) for row in self.db.execute(stmt)]


class SqlStagingDocumentWriter:
    """Adapter implementing ``StagingDocumentWriter`` with a native PostgreSQL upsert."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def save(self, record: StagingDocumentDTO) -> None:
        upsert_staging_document(self.db, record)


def upsert_staging_document(db: Session, record: StagingDocumentDTO) -> None:
    """
    Persists a validated and structured document in the Staging layer.

    Uses a native PostgreSQL 'UPSERT' command. If the document identifier is new,
    it performs an INSERT. If it already exists (a reprocessing scenario due to
    source changes), it performs an UPDATE, replacing outdated values with new
    ones extracted from the Pydantic model.

    Args:
        db (Session): Active SQLAlchemy session.
        record (StagingDocumentDTO): DTO object validated against ISAD(G) rules.
    """

    staging_dict = record.model_dump(exclude_unset=True)
    stmt = insert(StagingDocument).values(staging_dict)

    # Only the columns actually present in the payload may be overwritten. Iterating
    # over ``stmt.excluded`` would expose EVERY table column, resetting ``created_at``
    # and nulling out fields that simply were not sent (e.g. ISAD(G) metadata).
    immutable_columns = {"description_id", "created_at"}
    update_dict = {key: stmt.excluded[key] for key in staging_dict if key not in immutable_columns}

    if update_dict:
        stmt = stmt.on_conflict_do_update(index_elements=["description_id"], set_=update_dict)

    db.execute(stmt)
