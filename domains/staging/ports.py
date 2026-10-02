from collections.abc import Sequence
from typing import Any, Protocol


class RawRecordSource(Protocol):
    """
    Input port: provides raw records waiting to be structured by the Staging layer.

    The staging use case depends on this contract, not on the ingestion ORM. Any
    implementation (SQL, in-memory, remote API) that yields raw payloads with the
    expected keys can be plugged in.
    """

    def next_batch(self) -> Sequence[dict[str, Any]]:
        """
        Returns the raw records that are new or whose source content changed.

        Each record is a mapping with at least ``description_id``, ``payload``,
        ``content_hash`` and ``raw_title``.
        """
        ...


class StagingDocumentWriter(Protocol):
    """Output port: persists a structured document in the Staging layer."""

    def save(self, record: Any) -> None: ...
