"""The failures screen: what is breaking, how often, and since when."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.repository.failure_repo import FailureRepository
from memoria_curitibana.domains.archive.schemas.system_schema import FailureGroupListResponse

#: The window is a parameter, but bounded on both ends: an unbounded one would read the whole ledger
#: every time somebody opens the screen, and the question this answers is about what is happening
#: *now*, not about the archaeology of a failure fixed two years ago.
DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 365
MAX_GROUPS = 100


class FailureService:
    """Reads the grouped failures of the worker ledger and of the API ledger."""

    def __init__(self, db: Session) -> None:
        self.failures = FailureRepository(db)

    def list_groups(
        self, *, days: int = DEFAULT_WINDOW_DAYS, worker: str | None = None, limit: int = 20
    ) -> FailureGroupListResponse:
        """One line per root cause seen in the last ``days`` days, most recent first."""
        window = max(1, min(days, MAX_WINDOW_DAYS))
        since = datetime.now(UTC) - timedelta(days=window)
        items, total = self.failures.list_groups(since=since, worker=worker, limit=max(1, min(limit, MAX_GROUPS)))
        return FailureGroupListResponse(items=items, total=total)
