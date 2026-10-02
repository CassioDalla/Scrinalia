from collections.abc import Iterator
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class StagingRecord(BaseModel):
    """Read model of a structured staging document, decoupled from the staging ORM."""

    description_id: str
    title: str
    document_date: date | None = None
    raw_content_hash: str
    thumb_down_link: str | None = None
    indexing_points: str | None = None

    reference_code: str | None = None
    level: str | None = None
    producers: str | None = None
    admin_bio_history: str | None = None
    admin_archival_history: str | None = None
    provenance: str | None = None
    scope_content: str | None = None
    language_name: str | None = None
    archivist_notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StagingRecordSource(Protocol):
    """
    Input port of the archive transfer: yields structured staging records.

    The archive uses this instead of importing `domains.staging.models`, keeping the
    staging->archive boundary a contract rather than a cross-domain table join.
    """

    def stream(self, batch_size: int) -> Iterator[StagingRecord]: ...
