"""The cap one bounded run may touch, shared by the workers that sweep the collection.

``--limit N`` exists so a trial costs N units instead of the collection: measuring a threshold
against 4.844 documents when the question is "what does 0.60 do to the first twenty?" is how a
bench becomes an overnight run. It is deliberately **not** a persisted setting — a cap that
outlived the command would be a trap — so the runner refuses it for a worker that does not declare
it, and this object lives inside one ``execute`` call.

Two facts are worth one definition here rather than five: the cap counts the units the run
**touches** (an attempt, not a success — otherwise a queue of failures could never let a bounded run
end), and a batch may never be larger than what is left of the cap, so no run overshoots its bound.
"""

from dataclasses import dataclass


@dataclass
class RunBudget:
    """How many units are left in a bounded run; ``limit=None`` means the whole queue."""

    limit: int | None = None
    touched: int = 0

    @property
    def exhausted(self) -> bool:
        """True when the run has already touched the units it was allowed."""
        return self.limit is not None and self.touched >= self.limit

    def batch_size(self, db_batch_size: int) -> int:
        """Rows the next batch may fetch: the batch size, narrowed by what is left of the cap."""
        if self.limit is None:
            return db_batch_size
        return max(min(db_batch_size, self.limit - self.touched), 0)

    def spend(self, units: int) -> None:
        """Records the units this batch touched, whether or not each one succeeded."""
        self.touched += units
