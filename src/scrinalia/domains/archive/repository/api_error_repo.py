"""The API's own failure ledger, and the writer that keeps it out of the request's way.

``WorkerRunLedger`` records executions; this records the unexpected HTTP failures, and it follows the
same rule the execution ledger does: the write opens **its own committed session** and never raises.
The request's transaction has already been rolled back by the time an unhandled exception is handled,
so a row written there would vanish — and a bookkeeping table must never be the reason a failure that
was already answered as a 500 becomes a different failure on the way out.

Only *unexpected* failures belong here. A 404, a 409 or a 422 is an answer the API owes a client, not
a defect; recording those would bury the real ones under the ordinary noise of a filled-in form.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from scrinalia.core.database import SessionFactory, create_session
from scrinalia.core.logger import logger
from scrinalia.domains.archive.models.operations import MAX_ERROR_LENGTH, ApiError


class ApiErrorRepository:
    """Reads and writes the HTTP failure ledger; the caller owns the transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        request_id: str | None,
        method: str,
        path: str,
        status_code: int,
        error_kind: str,
        error: str,
    ) -> None:
        """Stores one failure. The class goes in front of the message: the fingerprint reads it."""
        message = f"{error_kind}: {error}" if error else error_kind
        self.db.add(
            ApiError(
                request_id=request_id,
                method=method[:10],
                path=path[:400],
                status_code=status_code,
                message=message[:MAX_ERROR_LENGTH],
            )
        )
        self.db.flush()


class ApiErrorRecorder:
    """Writes one line per unexpected HTTP failure, in its own transaction; never raises."""

    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def record(
        self,
        *,
        request_id: str | None,
        method: str,
        path: str,
        status_code: int,
        exc: BaseException,
    ) -> None:
        try:
            with self._session_factory() as db:
                ApiErrorRepository(db).record(
                    request_id=request_id,
                    method=method,
                    path=path,
                    status_code=status_code,
                    error_kind=type(exc).__name__,
                    error=str(exc),
                )
                db.commit()
        except Exception as failure:
            # The failure of the failure ledger goes to the log and nowhere else: the response is
            # already committed to being a 500, and turning it into a different one helps nobody.
            logger.error(f"⚠️ Não foi possível registrar a falha da API: {failure}")
