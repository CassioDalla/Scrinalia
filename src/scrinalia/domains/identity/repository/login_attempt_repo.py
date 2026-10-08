"""The writer of the failed-login counter, and why it cannot use the request's transaction.

A failed sign-in raises, and ``provide_unit_of_work`` rolls the request back on the way out — so a
counter incremented inside that transaction would be erased by the very failure it is counting, and
the account would never lock. The write therefore goes through **its own committed session**, exactly
like ``archive_worker_runs`` and the API's failure ledger, and it is fire-and-forget: bookkeeping must
never turn a refused login into a different failure.

The counter lives in the row (``auth_users.failed_attempts`` / ``locked_until``) and not in an
in-process map: a lockout that a restart forgets is a lockout a restart defeats, and the API runs
under ``--reload``. The backoff rides on the count itself — the *n*-th lockout doubles the window — so
there is no second column to keep in step with the first.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from scrinalia.core.config import get_settings
from scrinalia.core.database import SessionFactory, create_session
from scrinalia.core.logger import logger
from scrinalia.domains.identity.models import AuthUser


class LoginAttemptRepository:
    """Reads and writes the lockout state of one account; the caller owns the transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record_failure(self, user_id: int, *, now: datetime | None = None) -> None:
        """
        Counts one failed sign-in and locks the account when the count reaches the threshold.

        The row is taken ``FOR UPDATE``: two failures racing for the same account must produce two
        increments, and a lost update would hand a guesser a free attempt. When the count is a
        multiple of the threshold a lockout starts, and its length doubles with each further one up
        to ``AUTH_LOGIN_LOCKOUT_MAX_MINUTES`` — a fixed window would hand the guesser a schedule.
        """
        settings = get_settings()
        user = self.db.get(AuthUser, user_id, with_for_update=True)
        if user is None:
            # The account vanished between the failed verification and this write. Nothing to count,
            # and an error here would replace the answer the client already earned.
            return

        moment = now or datetime.now(UTC)
        user.failed_attempts += 1

        threshold = max(1, settings.AUTH_LOGIN_MAX_ATTEMPTS)
        if user.failed_attempts % threshold == 0:
            lockouts = user.failed_attempts // threshold
            minutes = min(
                settings.AUTH_LOGIN_LOCKOUT_MINUTES * 2 ** (lockouts - 1),
                settings.AUTH_LOGIN_LOCKOUT_MAX_MINUTES,
            )
            user.locked_until = moment + timedelta(minutes=minutes)
        self.db.flush()


class LoginAttemptRecorder:
    """Writes one failed sign-in in its own committed transaction; never raises."""

    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def record_failure(self, user_id: int) -> None:
        try:
            with self._session_factory() as db:
                LoginAttemptRepository(db).record_failure(user_id)
                db.commit()
        except Exception as failure:
            # The failure of the counter goes to the log and nowhere else: the refusal is already
            # decided, and turning it into a 500 would tell the guesser more than the lockout does.
            logger.error(f"⚠️ Não foi possível registrar a tentativa de login: {failure}")
