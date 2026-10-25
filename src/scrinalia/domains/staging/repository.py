from typing import TypeVarTuple

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from scrinalia.domains.ingestion.models import RawData
from scrinalia.domains.staging.models import StagingDocument
from scrinalia.domains.staging.schemas import RawRecord, StagingDocumentDTO

#: SQLAlchemy 2.1 made ``Select`` generic over **each selected column** instead of one row tuple,
#: so the columns of whatever statement reaches ``_with_pending`` have to travel through it as a
#: type-var tuple. ``Select[Any]`` meant "one column of Any" and stopped accepting a four-column
#: select; this keeps the caller's own types.
_Ts = TypeVarTuple("_Ts")


class SqlRawRecordSource:
    """
    Adapter implementing ``RawRecordSource`` on top of PostgreSQL.

    This is the ONLY place that knows about the ingestion ``RawData`` model: it
    performs the CDC (Change Data Capture) comparison by content hash so the
    application layer never joins across domains itself.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _with_pending(
        stmt: Select[*_Ts],
        force: bool,
        after: str | None,
        origin_code: str | None = None,
        description_id: str | None = None,
    ) -> Select[*_Ts]:
        """
        The one definition of "pending", applied to whatever statement needs it.

        The batch and the count both come through here, so "how many remain" cannot disagree with
        "what the next run takes" — the same reason the archive side has one CDC key.

        ``after`` is a keyset cursor on ``description_id`` and exists for the one case the CDC cannot
        advance on its own: ``force`` bypasses the hash comparison, so a bounded forced re-parse
        would otherwise re-read the same first page every run. It changes neither the CDC nor what
        counts as pending — only where the window starts.

        ``origin_code`` is the ingestion worker's window: a run of one origin must not stage another
        origin's records. ``description_id`` is the manual entry's window: the record the archivist
        just typed is staged in the same request, without touching the rest of the backlog.
        """
        if not force:
            stmt = stmt.outerjoin(StagingDocument, RawData.description_id == StagingDocument.description_id).where(
                (StagingDocument.description_id.is_(None)) | (StagingDocument.raw_content_hash != RawData.content_hash)
            )
        if after is not None:
            stmt = stmt.where(RawData.description_id > after)
        if origin_code is not None:
            stmt = stmt.where(RawData.origin_code == origin_code)
        if description_id is not None:
            stmt = stmt.where(RawData.description_id == description_id)
        return stmt

    def next_batch(
        self,
        force: bool = False,
        limit: int | None = None,
        after: str | None = None,
        origin_code: str | None = None,
        description_id: str | None = None,
    ) -> list[RawRecord]:
        """
        Pending records by CDC, or every record when ``force`` asks for a full re-parse.

        ``limit`` is applied **after** the CDC join, on the statement the join and the cursor already
        filtered: a limit inside the join would change which records count as pending, because the
        rows it excluded would never reach the comparison. The order is by ``description_id`` so a
        bounded run is reproducible and a cursor can name where the next one starts.
        """
        stmt = self._with_pending(
            select(
                RawData.description_id,
                RawData.origin_code,
                RawData.payload,
                RawData.content_hash,
                RawData.raw_title,
            ),
            force,
            after,
            origin_code,
            description_id,
        ).order_by(RawData.description_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [RawRecord.model_validate(row._mapping) for row in self.db.execute(stmt)]

    def count_pending(
        self,
        force: bool = False,
        after: str | None = None,
        origin_code: str | None = None,
        description_id: str | None = None,
    ) -> int:
        """How many raw records the same predicate still leaves pending."""
        stmt = self._with_pending(select(func.count()).select_from(RawData), force, after, origin_code, description_id)
        return int(self.db.scalar(stmt) or 0)


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
