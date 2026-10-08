from collections.abc import Iterator
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from scrinalia.core.content_hash import ContentHash


class StagingRecord(BaseModel):
    """Read model of a structured staging document, decoupled from the staging ORM."""

    description_id: str
    title: str
    document_date: date | None = None
    raw_content_hash: str
    thumb_down_link: str | None = None
    indexing_points: str | None = None

    reference_code: str | None = None
    #: The parent the source declares, by reference code, and the full path when it sends one. Both
    #: are optional because the origin is allowed to say nothing — and to deliver a child first.
    parent_reference_code: str | None = None
    hierarchy_path: str | None = None
    level: str | None = None
    producers: str | None = None
    admin_bio_history: str | None = None
    admin_archival_history: str | None = None
    provenance: str | None = None
    scope_content: str | None = None
    language_name: str | None = None
    archivist_notes: str | None = None
    #: ISAD(G) 4.1. It was parsed into staging from the beginning and had no counterpart here, so
    #: the transfer never carried it and the archive lost it. Declaring it changes
    #: ``parsed_content_hash`` for every row, which is the *intended* effect of the CDC contract:
    #: the next transfer re-reads the collection and the restriction reaches the archive.
    access_conditions: str | None = None

    model_config = ConfigDict(from_attributes=True)

    def parsed_content_hash(self) -> str:
        """
        Hash of what this layer *parsed*, used as the archive CDC key.

        The raw payload hash cannot see a parser change: fixing the date parser leaves the
        source byte-identical, so the archive would keep the old value forever. Hashing the
        parsed record makes the transfer notice it, exactly like a real source change.
        """
        return str(ContentHash.of(self.model_dump(mode="json")))


class StagingRecordSource(Protocol):
    """
    Input port of the archive transfer: yields structured staging records.

    The archive uses this instead of importing `domains.staging.models`, keeping the
    staging->archive boundary a contract rather than a cross-domain table join.
    """

    def stream(self, batch_size: int) -> Iterator[StagingRecord]: ...
