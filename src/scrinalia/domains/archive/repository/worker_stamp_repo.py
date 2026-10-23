"""Readings of the per-worker stamps, for the operations panel.

Every worker that stamps a unit writes into a JSONB ``execution_log``: ``ArchiveDocument`` for the
document workers, ``ArchiveTag`` for the macro-category classifier. "Processed" and "failed" are
therefore the same query for all of them, and they live here once instead of in nine worker
modules. The *pending* predicate is the opposite: it is bespoke per worker (each one filters
different columns and different governance rules), so it stays in the worker module.

The reading is a **breakdown**, not one number, because an identity-keyed slot can hold three
different things and the panel owes the operator the difference: a fingerprint (a value the slot's
own pattern accepts, which really names the producer), a legacy value (``"DONE"`` or
``PRODUCER_UNKNOWN`` — a run is recorded and its producer is not) and a failure mark. ``processed``
is the first two plus the failure, derived here from the same aggregate: a separate "the key is
present" query is the second definition this replaces.

The dependency is expressed as a Protocol, not by importing ``WorkerSpec``: a repository must not
reach into the workers package, and the catalogue already depends on the repository's readings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveDocument, ArchiveTag
from scrinalia.domains.archive.worker_stamp import FAILURE_STAMP_VALUES, IdentityStamp


@dataclass(frozen=True)
class StampBreakdown:
    """What the units of one worker's ledger carry, told apart by the slot's own vocabulary."""

    fingerprinted: int
    legacy: int
    failed: int
    unrecorded: int

    @property
    def processed(self) -> int:
        """Units whose log carries the key at all, whatever the value names."""
        return self.fingerprinted + self.legacy + self.failed


class StampedWorker(Protocol):
    """The part of a worker specification this repository needs (read-only, like the dataclass)."""

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def stamp(self) -> IdentityStamp | None:
        raise NotImplementedError

    @property
    def stamp_model(self) -> Literal["document", "tag"] | None:
        raise NotImplementedError


class WorkerStampRepository:
    """Reads what a worker's ledger already recorded, without touching its queue predicate."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _stamped_model(self, spec: StampedWorker) -> type[ArchiveDocument] | type[ArchiveTag]:
        if spec.stamp is None or spec.stamp_model is None:
            raise ValueError(f"Worker '{spec.name}' has no stamp to read.")
        return ArchiveDocument if spec.stamp_model == "document" else ArchiveTag

    def count_stamp_breakdown(self, spec: StampedWorker) -> StampBreakdown:
        """
        The four numbers of one identity-keyed slot, in one aggregate over the worker's own model.

        "Is this a fingerprint?" is answered by the slot's own ``fingerprint_pattern`` — the very
        expression ``mark_value`` validates against on the write path — so the panel and the worker
        cannot disagree about what an attributed unit is. ``PRODUCER_UNKNOWN`` and the ``"DONE"``
        written before it had a name land in ``legacy``: a run is recorded and its producer is not,
        which is exactly the distinction the old single number hid.

        The value is coalesced so a JSON ``null`` is a legacy value and not a unit counted in no
        bucket: the four numbers must add up to the model's own count.
        """
        model = self._stamped_model(spec)
        stamp = spec.stamp
        if stamp is None:  # ``_stamped_model`` already refused this; the annotation needs the check.
            raise ValueError(f"Worker '{spec.name}' has no stamp to read.")
        value = func.coalesce(model.execution_log[stamp.key].astext, "")  # type: ignore[union-attr]
        has_key = model.execution_log.has_key(stamp.key)  # type: ignore[union-attr]
        # ``ArchiveTag.execution_log`` is nullable, and ``NULL ? 'key'`` is NULL, not false: a tag with
        # no log at all has to be counted as unrecorded or the four numbers stop adding up.
        unrecorded = or_(model.execution_log.is_(None), ~has_key)  # type: ignore[union-attr]
        is_fingerprint = value.regexp_match(stamp.fingerprint_pattern.pattern)
        is_failure = value.in_(FAILURE_STAMP_VALUES)
        row = self.db.execute(
            select(
                func.count().filter(and_(has_key, is_fingerprint)).label("fingerprinted"),
                func.count().filter(and_(has_key, ~is_failure, ~is_fingerprint)).label("legacy"),
                func.count().filter(and_(has_key, is_failure)).label("failed"),
                func.count().filter(unrecorded).label("unrecorded"),
            ).select_from(model)
        ).one()
        return StampBreakdown(
            fingerprinted=int(row.fingerprinted),
            legacy=int(row.legacy),
            failed=int(row.failed),
            unrecorded=int(row.unrecorded),
        )
