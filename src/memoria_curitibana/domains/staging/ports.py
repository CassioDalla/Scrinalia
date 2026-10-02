from collections.abc import Sequence
from typing import Protocol

from memoria_curitibana.domains.staging.schemas import RawRecord, StagingDocumentDTO


class RawRecordSource(Protocol):
    """
    Input port: provides raw records waiting to be structured by the Staging layer.

    The staging use case depends on this contract, not on the ingestion ORM. Any
    implementation (SQL, in-memory, remote API) that yields ``RawRecord`` DTOs can
    be plugged in.
    """

    def next_batch(self) -> Sequence[RawRecord]:
        """Returns the raw records that are new or whose source content changed."""
        ...


class StagingDocumentWriter(Protocol):
    """Output port: persists a structured document in the Staging layer."""

    def save(self, record: StagingDocumentDTO) -> None: ...
