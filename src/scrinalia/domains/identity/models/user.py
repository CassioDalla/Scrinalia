"""The account: who may write, and with which role.

The first table of the project whose subject is not the collection but the *installation*. It is
deliberately small, and it has no ``deleted`` state: an account is deactivated (``is_active``), never
removed, because every ledger in the archive stores who decided what — ``changed_by_user_id`` is
``SET NULL``, so deleting the account would erase the *who* of decisions that still stand. Deactivating
keeps the name readable and takes the access away, which is the two separate things an archive needs.

``must_change_password`` exists for the one flow that creates a password nobody chose: the CLI's
bootstrap, which prints a temporary password to the operator's terminal. The account cannot be used
normally until the person replaces it, so the password in the shell's scrollback stops being a
credential.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base
from scrinalia.domains.identity.domain.permissions import Role


class AuthUser(Base):
    """
    One person who can sign in.

    ``email`` is stored **normalised** (lowercased, trimmed) and is unique: the normalisation is what
    makes the unique index mean "one account per person" instead of "one account per spelling". The
    domain owns the normalisation (``normalize_email``) and the repository is the only writer.

    ``failed_attempts``/``locked_until`` are columns and not an in-process counter: a lockout that
    disappears when the API restarts is a lockout that a restart defeats, and the API runs under
    ``--reload``. **The writer is the login path, and it cannot be the request transaction**: a failed
    login raises, and ``provide_unit_of_work`` rolls back on the way out, so a counter incremented
    there would be erased by the very failure it is counting. The write has to go through its own
    committed session, exactly like ``archive_worker_runs`` — which is why the enforcement lands with
    that writer and not as a side effect of ``authenticate``.
    """

    __tablename__ = "auth_users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    #: The argon2id hash. Text and not a fixed length on purpose: the parameters live inside the
    #: string, so raising the cost later keeps every existing hash verifiable.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
