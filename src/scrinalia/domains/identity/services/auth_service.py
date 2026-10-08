"""The rules of signing in, of keeping a session, and of administering accounts.

This is the layer that decides, and it is deliberately the only one: the repositories know SQL, the
domain knows how to hash and what a role may do, and everything that is a *policy* — how long a
session lives, when it slides, what "the same person" means, what happens to the other devices when a
password changes — is here, in one readable place.

It never commits. ``provide_unit_of_work`` owns the transaction, so a login that fails halfway leaves
nothing behind, and the CLI wraps the same service in the same unit of work.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scrinalia.core.config import get_settings
from scrinalia.domains.identity.domain.credentials import (
    check_password_policy,
    generate_session_token,
    hash_password,
    hash_session_token,
    needs_rehash,
    normalize_email,
    verify_decoy,
    verify_password,
)
from scrinalia.domains.identity.domain.permissions import Role
from scrinalia.domains.identity.exceptions import (
    DuplicateUserEmailError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    LastAdminError,
    SessionNotFoundError,
    UserNotFoundError,
)
from scrinalia.domains.identity.models import AuthSession, AuthUser
from scrinalia.domains.identity.repository.session_repo import SessionRepository
from scrinalia.domains.identity.repository.user_repo import UserRepository
from scrinalia.domains.identity.schemas.user_schema import (
    CreateUserCommand,
    UpdateUserCommand,
)

#: The single sentence a failed sign-in gets, whatever the reason. See ``InvalidCredentialsError``:
#: distinguishing "no such account" from "wrong password" is a user-enumeration oracle, and the person
#: who needs the distinction has the account list to consult.
INVALID_CREDENTIALS_MESSAGE = "E-mail ou senha inválidos."


class AuthService:
    """Sign-in, sessions and the account lifecycle, over one request's transaction."""

    def __init__(self, users: UserRepository, sessions: SessionRepository) -> None:
        self.users = users
        self.sessions = sessions

    # --- Signing in -----------------------------------------------------------------------------

    def authenticate(self, email: str, password: str) -> AuthUser:
        """
        The account behind these credentials, or a refusal.

        Every branch spends the same time: an unknown address is verified against a decoy hash, so
        the answer cannot be told apart from a wrong password by a stopwatch.
        """
        user = self.users.get_by_email(email)
        if user is None:
            verify_decoy(password)
            raise InvalidCredentialsError(INVALID_CREDENTIALS_MESSAGE)

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError(INVALID_CREDENTIALS_MESSAGE)

        if not user.is_active:
            # Same sentence on purpose: a deactivated account is a fact about the installation, and
            # confirming it to an anonymous caller confirms that the address was once real.
            raise InvalidCredentialsError(INVALID_CREDENTIALS_MESSAGE)

        return user

    def login(
        self,
        email: str,
        password: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, AuthUser]:
        """
        Authenticates and opens a session, returning the **raw** token and the account.

        The raw token is returned exactly once, to be put in the cookie: only its digest reaches the
        database, so this is the last moment it exists in the process. The password is rehashed here
        if the stored one used weaker parameters than the current configuration.
        """
        user = self.authenticate(email, password)
        now = datetime.now(UTC)

        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = now
        self.users.save(user)

        token = generate_session_token()
        self.sessions.issue(
            user_id=user.user_id,
            token_hash=hash_session_token(token),
            expires_at=self._expiry(now),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return token, user

    def resolve_session(self, token: str) -> AuthUser | None:
        """
        The account a cookie identifies, or ``None``. This runs on every authenticated request.

        The sliding renewal is throttled: pushing ``expires_at`` forward on every request would turn
        every read into a write. A session is only touched once it has been idle for
        ``AUTH_SESSION_TOUCH_MINUTES``, which is also why the idle window and the total lifetime are
        two different settings.
        """
        now = datetime.now(UTC)
        found = self.sessions.resolve(hash_session_token(token), now)
        if found is None:
            return None

        session, user = found
        touch_after = timedelta(minutes=get_settings().AUTH_SESSION_TOUCH_MINUTES)
        if session.last_seen_at + touch_after <= now:
            self.sessions.touch(session, now=now, expires_at=self._expiry(now))
        return user

    def logout(self, token: str) -> bool:
        """Ends the session the cookie names. ``False`` when it was already over."""
        return self.sessions.revoke_by_token_hash(hash_session_token(token), datetime.now(UTC))

    # --- The account's own password -------------------------------------------------------------

    def change_password(
        self,
        user: AuthUser,
        current_password: str,
        new_password: str,
        *,
        keep_token: str | None = None,
    ) -> AuthUser:
        """
        Replaces the password, proving the current one.

        Every other session of this account is ended: a password change is what a person does when
        they suspect the old one is known, and leaving the other devices signed in would answer the
        suspicion with nothing. ``keep_token`` spares the device making the change, so the archivist
        is not logged out of the screen they are standing on.
        """
        if not verify_password(current_password, user.password_hash):
            raise InvalidCurrentPasswordError("A senha atual não confere.")

        check_password_policy(new_password, email=user.email)
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        self.users.save(user)

        self.sessions.revoke_all_for_user(
            user.user_id,
            datetime.now(UTC),
            except_token_hash=hash_session_token(keep_token) if keep_token else None,
        )
        return user

    # --- Administration -------------------------------------------------------------------------

    def list_users(self) -> list[AuthUser]:
        return self.users.list_all()

    def get_user(self, user_id: int) -> AuthUser:
        user = self.users.get(user_id)
        if user is None:
            raise UserNotFoundError(f"Conta {user_id} não encontrada.")
        return user

    def list_sessions(self, user_id: int) -> list[AuthSession]:
        """
        The live sessions of one account, most recently seen first.

        The account is resolved before the list, so an unknown id is a 404 and not an empty list:
        "this account has no open sessions" and "there is no such account" are different answers, and
        an administrator who mistyped an id needs the second one.
        """
        self.get_user(user_id)
        return self.sessions.list_active_for_user(user_id, datetime.now(UTC))

    def revoke_session(self, user_id: int, session_id: int) -> AuthSession:
        """
        Ends one session of one account.

        An id that does not exist, or that belongs to another account, is the same refusal — see
        ``SessionNotFoundError``: the alternative answers "that id is real, just not here", which is
        an enumeration of other people's sessions.
        """
        self.get_user(user_id)
        session = self.sessions.get(session_id)
        if session is None or session.user_id != user_id:
            raise SessionNotFoundError(f"Sessão {session_id} não encontrada para esta conta.")
        self.sessions.revoke(session, datetime.now(UTC))
        return session

    def revoke_all_sessions(self, user_id: int) -> int:
        """Ends every live session of an account — the "sign out everywhere" an administrator needs."""
        self.get_user(user_id)
        return self.sessions.revoke_all_for_user(user_id, datetime.now(UTC))

    def create_user(self, command: CreateUserCommand, *, must_change_password: bool = False) -> AuthUser:
        """
        Creates an account.

        ``must_change_password`` is set by the CLI when it generates the password itself: a temporary
        password that the operator read off a terminal must not become the account's permanent one.
        """
        email = normalize_email(command.email)
        if self.users.get_by_email(email) is not None:
            raise DuplicateUserEmailError(f"Já existe uma conta com o e-mail {email}.")

        check_password_policy(command.password, email=email)
        return self.users.create(
            email=email,
            name=command.name.strip(),
            password_hash=hash_password(command.password),
            role=command.role,
            must_change_password=must_change_password,
        )

    def reset_password(self, user: AuthUser, new_password: str, *, must_change: bool = True) -> AuthUser:
        """
        An administrator sets a password without knowing the old one.

        The failed-attempt state is cleared with it — a reset that left the lockout in place would
        hand the person a new password and keep them out — and every session ends, for the same reason
        ``change_password`` ends them.
        """
        check_password_policy(new_password, email=user.email)
        user.password_hash = hash_password(new_password)
        user.must_change_password = must_change
        user.failed_attempts = 0
        user.locked_until = None
        self.users.save(user)
        self.sessions.revoke_all_for_user(user.user_id, datetime.now(UTC))
        return user

    def update_user(self, user: AuthUser, command: UpdateUserCommand) -> AuthUser:
        """
        Changes the name, the role or the activation of an account.

        Two rules ride along. Losing the last active administrator is refused, because it is the one
        lockout with no way back through the UI. And deactivating an account ends its sessions
        immediately: the flag alone would let whoever holds the cookie keep working until it expires.
        """
        self._guard_last_admin(user, command)

        if command.name is not None:
            user.name = command.name.strip()
        if command.role is not None:
            user.role = command.role
        if command.is_active is not None:
            user.is_active = command.is_active
        self.users.save(user)

        if command.is_active is False:
            self.sessions.revoke_all_for_user(user.user_id, datetime.now(UTC))
        return user

    def _guard_last_admin(self, user: AuthUser, command: UpdateUserCommand) -> None:
        """Refuses the change that would leave the installation without an active administrator."""
        loses_admin = command.is_active is False or (command.role is not None and command.role != Role.ADMIN)
        if not (user.role == Role.ADMIN and user.is_active and loses_admin):
            return
        if self.users.count_active_admins() <= 1:
            raise LastAdminError(
                "Esta é a última conta de administrador ativa; promova outra conta antes de alterar esta."
            )

    # --- Internals ------------------------------------------------------------------------------

    def _expiry(self, now: datetime) -> datetime:
        return now + timedelta(minutes=get_settings().AUTH_SESSION_TTL_MINUTES)
