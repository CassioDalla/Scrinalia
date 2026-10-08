"""Generic readings of the per-worker stamps, for the operations panel.

Every worker that stamps a unit writes into a JSONB ``execution_log``: ``ArchiveDocument`` for the
document workers, ``ArchiveTag`` for the macro-category classifier. "Processed" and "failed" are
therefore the same two queries for all of them, and they live here once instead of in nine worker
modules. The *pending* predicate is the opposite: it is bespoke per worker (each one filters
different columns and different governance rules), so it stays in the worker module.

The dependency is expressed as a Protocol, not by importing ``WorkerSpec``: a repository must not
reach into the workers package, and the catalogue already depends on the repository's readings.
"""

from __future__ import annotations

from typing import Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveDocument, ArchiveTag
from scrinalia.domains.archive.worker_stamp import FAILURE_STAMP_VALUES, WorkerStamp


class StampedWorker(Protocol):
    """The part of a worker specification this repository needs (read-only, like the dataclass)."""

    @property
    def name(self) -> str: ...

    @property
    def stamp(self) -> WorkerStamp | None: ...

    @property
    def stamp_model(self) -> Literal["document", "tag"] | None: ...


class WorkerStampRepository:
    """Counts what a worker's ledger already recorded, without touching its queue predicate."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _stamped_model(self, spec: StampedWorker) -> type[ArchiveDocument] | type[ArchiveTag]:
        if spec.stamp is None or spec.stamp_model is None:
            raise ValueError(f"Worker '{spec.name}' has no stamp to read.")
        return ArchiveDocument if spec.stamp_model == "document" else ArchiveTag

    def count_stamped(self, spec: StampedWorker) -> int:
        """Units whose log carries the worker's stamp key, whatever its value."""
        model = self._stamped_model(spec)
        stmt = select(func.count()).select_from(model).where(model.execution_log.has_key(spec.stamp.key))  # type: ignore[union-attr]
        return int(self.db.scalar(stmt) or 0)

    def count_stamp_failures(self, spec: StampedWorker) -> int:
        """
        Units whose stamp records a failure.

        A content-keyed stamp (the embedding's MD5, the macro-category's label fingerprint) never
        carries a failure value, so this answers zero for those workers — which is the truth: they
        do not mark a document as failed, they raise and stop.
        """
        model = self._stamped_model(spec)
        stmt = (
            select(func.count())
            .select_from(model)
            .where(model.execution_log[spec.stamp.key].astext.in_(FAILURE_STAMP_VALUES))  # type: ignore[union-attr]
        )
        return int(self.db.scalar(stmt) or 0)
