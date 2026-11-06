"""The contract of a diffusion adapter: the callable one channel's export runs.

The registry names the module and the worker resolves its ``execute``; this Protocol is the shape
that callable has, so an adapter is a module with one function and no class hierarchy. The concrete
adapter is #214 (the open dataset); the public site is ``LIVE`` and never runs.

The adapter owns the destination. It **must be idempotent**: a scheduled export that fails is
retried by the ledger's own policy (ADR 0015), so a second attempt may reach a destination the first
one partially wrote. Writing the whole snapshot again is the adapter's job, not the runner's.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from scrinalia.domains.archive.workers.cancellation import RunControl
from scrinalia.domains.diffusion.models import DiffusionChannel


class DiffusionAdapter(Protocol):
    """
    One channel's export, as the worker calls it.

    ``channel`` is the lifecycle row — its configuration and its run policy, already validated by the
    registry's model — and not a second copy of the definition. ``db_session`` is the run's session:
    the adapter reads the covered set and writes the destination through it. ``run_control`` is the
    cancellation the worker repeats at every batch boundary, and an adapter that writes in batches
    calls it between them.
    """

    def __call__(
        self,
        channel: DiffusionChannel,
        *,
        db_session: Session,
        run_control: RunControl | None = None,
    ) -> None:
        """Writes the channel's export; a failure is raised and the ledger records its cause."""
        raise NotImplementedError
