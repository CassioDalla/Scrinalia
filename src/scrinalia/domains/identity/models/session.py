"""The session: one sign-in, revocable, stored where the database can end it.

The cookie carries an opaque random token and the table stores only its **SHA-256**. Two consequences
that are the reason for the design: a leaked database dump contains no usable session, and a leaked
token can be revoked — which a signed stateless cookie cannot, except by shortening its life to the
point of logging people out mid-task.

The row is also the answer to "where am I signed in?", which the accounts screen needs, and to "sign
out everywhere", which is what an archivist wants the moment a laptop is lost. ``ON DELETE CASCADE``
is right here and nowhere else in this domain: a session has no meaning without its account, unlike a
decision, whose author's name must survive.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base


class AuthSession(Base):
    """
    One live sign-in.

    ``expires_at`` moves forward on use (see ``AuthService.resolve_session``), but only when the
    session has been idle for a while: writing ``last_seen_at`` on every request would turn every
    authenticated read into an UPDATE.
    """

    __tablename__ = "auth_sessions"

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: SHA-256 hex of the token in the cookie. The token itself is never stored, so the table cannot
    #: be replayed even by whoever reads it. Unique, and the unique index is also the lookup path:
    #: every authenticated request resolves the session by this column.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    #: Set instead of deleting the row, so "this session ended" is a fact with a time on it. The
    #: logout path writes it; ``NULL`` means the session was never explicitly ended.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Free-form context for the "active sessions" list. Truncated by the writer, never trusted.
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
