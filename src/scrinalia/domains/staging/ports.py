from collections.abc import Sequence
from typing import Protocol

from scrinalia.domains.staging.schemas import RawRecord, StagingDocumentDTO


class RawRecordSource(Protocol):
    """
    Input port: provides raw records waiting to be structured by the Staging layer.

    The staging use case depends on this contract, not on the ingestion ORM. Any
    implementation (SQL, in-memory, remote API) that yields ``RawRecord`` DTOs can
    be plugged in.
    """

    def next_batch(self, force: bool = False) -> Sequence[RawRecord]:
        """
        Returns the raw records that are new or whose source content changed.

        ``force`` ignores the content-hash comparison and returns everything: a parser
        change does not touch the source payload, so the CDC alone would never re-parse
        the collection.
        """
        ...


class StagingDocumentWriter(Protocol):
    """Output port: persists a structured document in the Staging layer."""

    def save(self, record: StagingDocumentDTO) -> None: ...
