"""The sessions table: issuing, resolving and ending sign-ins.

The resolution is one query with the join already applied, because it is the query that runs on
**every** authenticated request. Doing it in two steps (session, then user) would add a round trip to
each one, and the ``is_active`` filter has to be part of the same statement anyway — a deactivated
account must stop being resolvable the moment the flag flips, without waiting for a session to expire.
"""

from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from scrinalia.domains.identity.models import AuthSession, AuthUser


class SessionRepository:
    """Live sign-ins of one installation."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, session_id: int) -> AuthSession | None:
        """
        One session by id, revoked or not.

        The administrative read and the target of a revocation: both need the row even when it is no
        longer live, because the answer to "revoke this session" must not depend on the screen having
        listed it a second earlier.
        """
        return self.db.get(AuthSession, session_id)

    def issue(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthSession:
        session = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent[:300] if user_agent else None,
            ip_address=ip_address,
        )
        self.db.add(session)
        self.db.flush()
        return session

    def resolve(self, token_hash: str, now: datetime) -> tuple[AuthSession, AuthUser] | None:
        """
        The session and its account, or ``None``.

        Revoked, expired and deactivated all answer ``None``: from the client's side they are the same
        fact — this cookie no longer identifies anyone — and giving them different answers would turn
        the middleware into an oracle about accounts that no longer sign in.
        """
        row = self.db.execute(
            select(AuthSession, AuthUser)
            .join(AuthUser, AuthUser.user_id == AuthSession.user_id)
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthUser.is_active.is_(True),
            )
        ).first()
        if row is None:
            return None
        session, user = row
        return session, user

    def touch(self, session: AuthSession, *, now: datetime, expires_at: datetime) -> None:
        """Slides the session forward. Called only when it has been idle long enough to be worth it."""
        session.last_seen_at = now
        session.expires_at = expires_at
        self.db.flush()

    def revoke(self, session: AuthSession, now: datetime) -> None:
        """Ends one session, keeping the row so "this ended" has a time on it."""
        session.revoked_at = now
        self.db.flush()

    def revoke_by_token_hash(self, token_hash: str, now: datetime) -> bool:
        """Ends a session named by the cookie. ``False`` when there was nothing live to end."""
        result = cast(
            CursorResult,
            self.db.execute(
                update(AuthSession)
                .where(AuthSession.token_hash == token_hash, AuthSession.revoked_at.is_(None))
                .values(revoked_at=now)
            ),
        )
        return bool(result.rowcount)

    def revoke_all_for_user(self, user_id: int, now: datetime, *, except_token_hash: str | None = None) -> int:
        """
        Ends every live session of one account.

        The lever behind "change the password and the other devices stop": a password reset that left
        the old sessions alive would not have locked anyone out. ``except_token_hash`` is what keeps
        the device that *made* the change signed in — without it, replacing your own password logs you
        out of the screen you are standing on.
        """
        statement = (
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        if except_token_hash is not None:
            statement = statement.where(AuthSession.token_hash != except_token_hash)
        result = cast(CursorResult, self.db.execute(statement))
        return int(result.rowcount or 0)

    def list_active_for_user(self, user_id: int, now: datetime) -> list[AuthSession]:
        """The "where am I signed in?" list, newest first."""
        return list(
            self.db.scalars(
                select(AuthSession)
                .where(
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
                .order_by(AuthSession.last_seen_at.desc())
            ).all()
        )
