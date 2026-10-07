from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


class UnitOfWork:
    """
    Owns a single transaction boundary for one application use case.

    Services and repositories must never call ``commit``/``rollback`` themselves:
    they ``flush`` to obtain IDs, and the Unit of Work decides when the work is
    durable. This keeps multi-step operations (merge, transfer, enrichment) atomic
    and testable.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def flush(self) -> None:
        self.db.flush()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Runs a block as a savepoint, rolling back only that block on failure."""
        with self.db.begin_nested():
            yield self.db
