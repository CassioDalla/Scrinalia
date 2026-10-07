"""Reads and writes of the accounts table.

The repository stays dumb: it normalises nothing and hashes nothing. Both are policy and live in the
service and in ``domain/credentials.py``, so there is one place where "the same person" and "a
password" are defined. What the repository owns is the two invariants that only SQL can hold — the
unique address and the lookup by its normalised form.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scrinalia.domains.identity.domain.credentials import normalize_email
from scrinalia.domains.identity.domain.permissions import Role
from scrinalia.domains.identity.exceptions import InvalidEmailError
from scrinalia.domains.identity.models import AuthUser


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
