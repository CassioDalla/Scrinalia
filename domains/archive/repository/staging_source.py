from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from domains.archive.ports.staging_source import StagingRecord
from domains.staging.models import StagingDocument


class SqlStagingRecordSource:
    """
    Adapter implementing ``StagingRecordSource`` on top of the staging table.

    This is the ONLY archive-side module allowed to know the staging ORM. It maps
    each row to the ``StagingRecord`` read model before handing it to the transfer
    use case.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def stream(self, batch_size: int) -> Iterator[StagingRecord]:
        # yield_per avoids loading the whole table into memory.
        rows = self.db.scalars(select(StagingDocument)).yield_per(batch_size)
        for row in rows:
            yield StagingRecord.model_validate(row)
