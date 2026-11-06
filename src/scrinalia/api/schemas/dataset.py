"""The dataset export's HTTP shapes.

The preview is the operator's dry run (ADR 0024): record count, the exact size of each format, the
removals since the current snapshot and why a run would refuse. It is a *read* of the package that
would be written, so it carries the destination and the readiness sentence the card shows — the route
is ``OPERATE`` because only the operator configures and runs an export.
"""

from __future__ import annotations

from pydantic import BaseModel

from scrinalia.domains.diffusion.dataset_contract import DatasetArtifact
from scrinalia.domains.diffusion.dataset_writer import DatasetPreview


class DatasetPreviewDTO(BaseModel):
    """What a dataset export run would write, without writing it."""

    record_count: int
    artifacts: list[DatasetArtifact]
    removals: list[str]
    previous_snapshot_id: str | None
    snapshot_id: str
    unchanged: bool
    destination: str | None
    ready: bool
    reason: str | None

    @classmethod
    def from_preview(cls, preview: DatasetPreview) -> DatasetPreviewDTO:
        """Maps the domain value, field by field; the API never returns the dataclass itself."""
        return cls(
            record_count=preview.record_count,
            artifacts=list(preview.artifacts),
            removals=list(preview.removals),
            previous_snapshot_id=preview.previous_snapshot_id,
            snapshot_id=preview.snapshot_id,
            unchanged=preview.unchanged,
            destination=preview.destination,
            ready=preview.ready,
            reason=preview.reason,
        )
