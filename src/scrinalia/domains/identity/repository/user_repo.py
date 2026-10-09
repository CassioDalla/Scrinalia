"""Reads and writes of the accounts table.

The repository stays dumb: it normalises nothing and hashes nothing. Both are policy and live in the
service and in ``domain/credentials.py``, so there is one place where "the same person" and "a
password" are defined. What the repository owns is the invariants that only SQL can hold — the unique
address, the lookup by its normalised form, and the "at most one first administrator" of ADR 0011.
"""

from sqlalchemy import func, insert, literal, select, text
from sqlalchemy.orm import Session

from scrinalia.domains.identity.domain.credentials import normalize_email
from scrinalia.domains.identity.domain.permissions import Role
from scrinalia.domains.identity.exceptions import InvalidEmailError
from scrinalia.domains.identity.models import AuthUser

#: The lock that makes the first-run predicate atomic. ``EXCLUSIVE`` conflicts with itself, so two
#: first-run calls cannot interleave, and with the ``ROW EXCLUSIVE`` of an ordinary write, so the CLI
#: cannot create an account behind the route's back either. See :meth:`UserRepository.create_first_admin`
#: and ADR 0011.
LOCK_ACCOUNTS = text("LOCK TABLE auth_users IN EXCLUSIVE MODE")


class UserRepository:
    """Accounts of one installation."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: int) -> AuthUser | None:
        return self.db.get(AuthUser, user_id)

    def get_by_email(self, email: str) -> AuthUser | None:
        """Looks the account up by the normalised address, which is the only spelling stored."""
        try:
            normalized = normalize_email(email)
        except InvalidEmailError:
            # An address that cannot be normalised cannot have been stored, so the answer is "no
            # account" and not an error: the login path must answer the same thing for a malformed
            # address as for an unknown one, or the two are distinguishable.
            return None
        return self.db.scalars(select(AuthUser).where(AuthUser.email == normalized)).first()

    def has_any(self) -> bool:
        """
        Whether the installation has any account at all — the first-run predicate.

        A ``SELECT`` and not a ``COUNT``: the question is "is there one?" and the scan stops at the
        first row. It exists on its own because the steady state of the first-run route answers 409
        from here, **before** the password policy and argon2id are paid for (ADR 0011).
        """
        return self.db.scalar(select(AuthUser.user_id).limit(1)) is not None

    def create_first_admin(self, *, email: str, name: str, password_hash: str) -> AuthUser | None:
        """
        Creates the administrator of an **empty** installation, or ``None`` when one already exists.

        Two statements, and the first is the reason the second can be trusted:
        ``INSERT … SELECT … WHERE NOT EXISTS`` is a predicate over a snapshot, so two concurrent
        transactions under READ COMMITTED both insert — measured, two accounts (ADR 0011).
        ``LOCK TABLE … IN EXCLUSIVE MODE`` serializes the decision, and the ``INSERT`` that follows
        takes its snapshot *after* the lock was granted, so the call that waited evaluates the
        predicate against the committed row and inserts nothing.

        The role is not a parameter and the flags are not arguments: this is the installation's first
        account, so it administers, and it carries neither a temporary password nor a lockout — the
        person chose the password, and ``is_active``/``must_change_password``/``failed_attempts`` come
        from the model's own defaults. ``last_login_at`` **is** written, because the same call opens
        the session that signs this account in, and an accounts screen that showed "never signed in"
        beside somebody who is signed in would be lying about a column it can see.
        """
        self.db.execute(LOCK_ACCOUNTS)
        statement = (
            insert(AuthUser)
            .from_select(
                ["email", "name", "password_hash", "role", "last_login_at"],
                select(
                    literal(email),
                    literal(name),
                    literal(password_hash),
                    literal(Role.ADMIN, type_=AuthUser.__table__.c.role.type),
                    func.now(),
                ).where(~select(AuthUser.user_id).exists()),
            )
            .returning(AuthUser.user_id)
        )
        user_id = self.db.scalar(statement)
        if user_id is None:
            return None
        return self.db.get(AuthUser, user_id)

    def list_all(self) -> list[AuthUser]:
        """Every account, deactivated ones included: the screen shows the whole installation."""
        return list(self.db.scalars(select(AuthUser).order_by(AuthUser.name, AuthUser.user_id)).all())

    def count_active_admins(self) -> int:
        """How many administrators can still sign in. The guard of the last-admin rule."""
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(AuthUser)
                .where(AuthUser.role == Role.ADMIN, AuthUser.is_active.is_(True))
            )
            or 0
        )

    def create(
        self,
        *,
        email: str,
        name: str,
        password_hash: str,
        role: Role,
        must_change_password: bool = False,
    ) -> AuthUser:
        user = AuthUser(
            email=email,
            name=name,
            password_hash=password_hash,
            role=role,
            must_change_password=must_change_password,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def save(self, user: AuthUser) -> AuthUser:
        self.db.flush()
        return user
