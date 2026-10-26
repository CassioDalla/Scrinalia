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

    def next_batch(
        self,
        force: bool = False,
        limit: int | None = None,
        after: str | None = None,
        origin_code: str | None = None,
        description_id: str | None = None,
        description_ids: Sequence[str] | None = None,
    ) -> Sequence[RawRecord]:
        """
        Returns the raw records that are new or whose source content changed.

        ``force`` ignores the content-hash comparison and returns everything: a parser
        change does not touch the source payload, so the CDC alone would never re-parse
        the collection.

        ``limit`` bounds one run and is applied **after** the comparison, never inside it, so a
        limited run leaves the rest pending instead of changing which records count as pending.
        ``after`` is a keyset cursor over ``description_id``: under the CDC a bounded run advances
        by itself (a processed record stops matching), but a ``force`` re-parse does not, so a
        bounded forced run names where the next one starts.

        ``origin_code`` bounds the run to one origin's records, ``description_id`` to the one
        record a manual entry just wrote, and ``description_ids`` to the exact window a batch
        import wrote (the CSV import). All three narrow the set; none changes what counts as
        pending for the records it leaves in scope.
        """
        raise NotImplementedError

    def count_pending(
        self,
        force: bool = False,
        after: str | None = None,
        origin_code: str | None = None,
        description_id: str | None = None,
        description_ids: Sequence[str] | None = None,
    ) -> int:
        """
        How many records the same predicate still leaves pending.

        It belongs to the port because it is the port's own definition of "pending": the run reports
        what remains through it instead of a second query written beside the source.
        """
        raise NotImplementedError


class StagingDocumentWriter(Protocol):
    """Output port: persists a structured document in the Staging layer."""

    def save(self, record: StagingDocumentDTO) -> None:
        raise NotImplementedError
