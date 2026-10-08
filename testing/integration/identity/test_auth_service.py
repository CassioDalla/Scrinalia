"""The sign-in policy, exercised against the real database and the real hasher.

These are integration tests because almost everything worth asserting here *is* state: a session that
survives a logout, a counter that a reset clears, a second device that stops working when the password
changes. A mocked repository would assert the mock.
"""

from datetime import UTC, datetime, timedelta

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select

from scrinalia.core.config import settings
from scrinalia.domains.identity.domain.credentials import (
    generate_session_token,
    hash_session_token,
    needs_rehash,
    verify_password,
)
from scrinalia.domains.identity.domain.permissions import Role
from scrinalia.domains.identity.exceptions import (
    AccountLockedError,
    DuplicateUserEmailError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    LastAdminError,
    SessionNotFoundError,
    UserNotFoundError,
    WeakPasswordError,
)
from scrinalia.domains.identity.models import AuthSession
from scrinalia.domains.identity.schemas.user_schema import CreateUserCommand, UpdateUserCommand

PASSWORD = "uma senha bem longa"
NEW_PASSWORD = "uma senha ainda mais longa"


# ==========================================
# SIGNING IN
# ==========================================


def test_login_returns_a_token_and_stores_only_its_digest(auth_service, generate_user, db_session) -> None:
    """The raw token exists in the process once. What the database holds cannot be replayed."""
    user = generate_user()

    token, authenticated = auth_service.login("maria@arquivo.org", PASSWORD)

    assert authenticated.user_id == user.user_id
    session = db_session.scalars(select(AuthSession)).one()
    assert session.token_hash == hash_session_token(token)
    assert session.token_hash != token


def test_login_accepts_the_address_in_any_spelling(auth_service, generate_user) -> None:
    generate_user(email="maria@arquivo.org")

    _, authenticated = auth_service.login("  Maria@Arquivo.ORG ", PASSWORD)

    assert authenticated.email == "maria@arquivo.org"


def test_login_records_when_it_happened(auth_service, generate_user) -> None:
    generate_user()

    _, authenticated = auth_service.login("maria@arquivo.org", PASSWORD)

    assert authenticated.last_login_at is not None


def test_a_wrong_password_is_refused(auth_service, generate_user) -> None:
    generate_user()

    with pytest.raises(InvalidCredentialsError):
        auth_service.login("maria@arquivo.org", "a senha errada")


def test_an_unknown_address_answers_exactly_like_a_wrong_password(auth_service, generate_user) -> None:
    """
    The user-enumeration guard.

    The two sentences are compared, not just the exception type: a different wording is the same
    oracle as a different status code.
    """
    generate_user()

    with pytest.raises(InvalidCredentialsError) as unknown:
        auth_service.login("ninguem@arquivo.org", PASSWORD)
    with pytest.raises(InvalidCredentialsError) as wrong:
        auth_service.login("maria@arquivo.org", "a senha errada")

    assert str(unknown.value) == str(wrong.value)


def test_a_deactivated_account_answers_like_an_unknown_one(auth_service, generate_user) -> None:
    generate_user(is_active=False)

    with pytest.raises(InvalidCredentialsError) as deactivated:
        auth_service.login("maria@arquivo.org", PASSWORD)
    with pytest.raises(InvalidCredentialsError) as unknown:
        auth_service.login("ninguem@arquivo.org", PASSWORD)

    assert str(deactivated.value) == str(unknown.value)


def test_login_upgrades_a_hash_made_with_weaker_parameters(auth_service, generate_user, db_session) -> None:
    """Raising the cost in settings reaches the accounts that already exist, one login at a time."""
    user = generate_user()
    user.password_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    db_session.flush()
    assert needs_rehash(user.password_hash) is True

    auth_service.login("maria@arquivo.org", PASSWORD)

    assert needs_rehash(user.password_hash) is False
    assert verify_password(PASSWORD, user.password_hash) is True


# ==========================================
# KEEPING A SESSION
# ==========================================


def test_a_live_session_resolves_to_its_account(auth_service, generate_user) -> None:
    user = generate_user()
    token, _ = auth_service.login("maria@arquivo.org", PASSWORD)

    resolved = auth_service.resolve_session(token)

    assert resolved is not None
    assert resolved.user_id == user.user_id


def test_logout_ends_the_session(auth_service, generate_user) -> None:
    generate_user()
    token, _ = auth_service.login("maria@arquivo.org", PASSWORD)

    assert auth_service.logout(token) is True

    assert auth_service.resolve_session(token) is None
    # The second logout is a no-op, not an error: the cookie may be sent twice by a reload.
    assert auth_service.logout(token) is False


def test_an_unknown_token_resolves_to_nobody(auth_service) -> None:
    assert auth_service.resolve_session(generate_session_token()) is None


def test_an_expired_session_is_not_resolved(auth_service, generate_user, db_session) -> None:
    user = generate_user()
    token = generate_session_token()
    auth_service.sessions.issue(
        user_id=user.user_id,
        token_hash=hash_session_token(token),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.flush()

    assert auth_service.resolve_session(token) is None


def test_deactivating_an_account_stops_its_sessions_at_once(auth_service, generate_user, db_session) -> None:
    """The flag alone would leave whoever holds the cookie working until it expires."""
    user = generate_user()
    token, _ = auth_service.login("maria@arquivo.org", PASSWORD)
    user.is_active = False
    db_session.flush()

    assert auth_service.resolve_session(token) is None


def test_the_session_slides_only_when_it_has_been_idle(auth_service, generate_user, db_session) -> None:
    """
    The renewal is throttled on purpose: touching it on every request would turn every read into a
    write, and the archivist would never notice except in the size of the write-ahead log.
    """
    generate_user()
    token, _ = auth_service.login("maria@arquivo.org", PASSWORD)
    session = db_session.scalars(select(AuthSession)).one()

    first_seen = session.last_seen_at
    first_expiry = session.expires_at
    auth_service.resolve_session(token)
    assert session.last_seen_at == first_seen
    assert session.expires_at == first_expiry

    session.last_seen_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.flush()

    auth_service.resolve_session(token)
    assert session.last_seen_at > first_seen
    assert session.expires_at > first_expiry


# ==========================================
# THE PASSWORD
# ==========================================


def test_changing_the_password_requires_the_current_one(auth_service, generate_user) -> None:
    user = generate_user()

    with pytest.raises(InvalidCurrentPasswordError):
        auth_service.change_password(user, "a senha errada", NEW_PASSWORD)

    assert verify_password(PASSWORD, user.password_hash) is True


def test_changing_the_password_ends_the_other_devices_and_keeps_the_current_one(auth_service, generate_user) -> None:
    """
    Both halves matter: a password change is what somebody does when they suspect the old one is
    known, and being logged out of the screen you are standing on is not what they asked for.
    """
    user = generate_user()
    token_one, _ = auth_service.login("maria@arquivo.org", PASSWORD)
    token_two, _ = auth_service.login("maria@arquivo.org", PASSWORD)

    auth_service.change_password(user, PASSWORD, NEW_PASSWORD, keep_token=token_one)

    assert auth_service.resolve_session(token_one) is not None
    assert auth_service.resolve_session(token_two) is None
    assert verify_password(NEW_PASSWORD, user.password_hash) is True
    assert verify_password(PASSWORD, user.password_hash) is False
    assert user.must_change_password is False


def test_a_password_below_the_policy_is_refused_on_the_way_in(auth_service, generate_user) -> None:
    user = generate_user()

    with pytest.raises(WeakPasswordError):
        auth_service.change_password(user, PASSWORD, "curta")


def test_resetting_a_password_clears_the_lockout_state_and_ends_every_session(
    auth_service, generate_user, db_session
) -> None:
    """
    A reset that left the lockout in place would hand the person a new password and keep them out.
    """
    user = generate_user(must_change_password=True)
    token, _ = auth_service.login("maria@arquivo.org", PASSWORD)
    user.failed_attempts = 4
    user.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    db_session.flush()

    auth_service.reset_password(user, NEW_PASSWORD)

    assert user.failed_attempts == 0
    assert user.locked_until is None
    assert user.must_change_password is True
    assert verify_password(NEW_PASSWORD, user.password_hash) is True
    assert auth_service.resolve_session(token) is None


# ==========================================
# ADMINISTERING ACCOUNTS
# ==========================================


def test_creating_an_account_normalises_the_address(auth_service) -> None:
    created = auth_service.create_user(
        CreateUserCommand(email="  Ana@Arquivo.ORG ", name=" Ana ", role=Role.CURATOR, password=PASSWORD)
    )

    assert created.email == "ana@arquivo.org"
    assert created.name == "Ana"


def test_the_same_address_cannot_be_created_twice(auth_service) -> None:
    """Case-insensitively: the normalisation is what makes the unique index mean one account."""
    auth_service.create_user(
        CreateUserCommand(email="ana@arquivo.org", name="Ana", role=Role.CURATOR, password=PASSWORD)
    )

    with pytest.raises(DuplicateUserEmailError):
        auth_service.create_user(
            CreateUserCommand(email="Ana@Arquivo.org", name="Outra Ana", role=Role.VIEWER, password=PASSWORD)
        )


def test_creating_an_account_refuses_a_weak_password(auth_service) -> None:
    with pytest.raises(WeakPasswordError):
        auth_service.create_user(
            CreateUserCommand(email="ana@arquivo.org", name="Ana", role=Role.CURATOR, password="curta")
        )


def test_a_bootstrap_account_can_be_flagged_to_change_its_password(auth_service) -> None:
    """The CLI generates the password it prints, so the account must not keep it."""
    created = auth_service.create_user(
        CreateUserCommand(email="ana@arquivo.org", name="Ana", role=Role.ADMIN, password=PASSWORD),
        must_change_password=True,
    )

    assert created.must_change_password is True


def test_the_last_active_admin_cannot_be_deactivated_or_demoted(auth_service, generate_user) -> None:
    """
    The one lockout with no way back through the screen: with every admin gone, nobody can create the
    next account, and the way in is the CLI on the host.
    """
    admin = generate_user(email="admin@arquivo.org", role=Role.ADMIN)

    with pytest.raises(LastAdminError):
        auth_service.update_user(admin, UpdateUserCommand(is_active=False))
    with pytest.raises(LastAdminError):
        auth_service.update_user(admin, UpdateUserCommand(role=Role.CURATOR))

    assert admin.is_active is True
    assert admin.role == Role.ADMIN


def test_a_second_admin_removes_the_guard(auth_service, generate_user) -> None:
    admin = generate_user(email="admin@arquivo.org", role=Role.ADMIN)
    generate_user(email="outro@arquivo.org", role=Role.ADMIN)

    updated = auth_service.update_user(admin, UpdateUserCommand(is_active=False))

    assert updated.is_active is False


def test_a_deactivated_viewer_does_not_trigger_the_admin_guard(auth_service, generate_user) -> None:
    """The guard is about administrators; it must not block an ordinary account from being closed."""
    generate_user(email="admin@arquivo.org", role=Role.ADMIN)
    viewer = generate_user(email="leitor@arquivo.org", role=Role.VIEWER)

    assert auth_service.update_user(viewer, UpdateUserCommand(is_active=False)).is_active is False


def test_deactivating_an_account_ends_its_sessions(auth_service, generate_user) -> None:
    user = generate_user()
    token, _ = auth_service.login("maria@arquivo.org", PASSWORD)

    auth_service.update_user(user, UpdateUserCommand(is_active=False))

    assert auth_service.resolve_session(token) is None


# ==========================================
# THE SESSIONS OF AN ACCOUNT
# ==========================================


def test_the_sessions_of_an_account_are_listed(auth_service, generate_user) -> None:
    """The "where am I signed in?" read: one row per live sign-in, and none of the ended ones."""
    user = generate_user()
    first_token, _ = auth_service.login("maria@arquivo.org", PASSWORD)
    second_token, _ = auth_service.login("maria@arquivo.org", PASSWORD)
    auth_service.logout(first_token)

    sessions = auth_service.list_sessions(user.user_id)

    assert len(sessions) == 1
    assert sessions[0].token_hash == hash_session_token(second_token)


def test_listing_the_sessions_of_an_unknown_account_is_a_not_found(auth_service) -> None:
    """
    An empty list would be a lie: it says "this account has no open sessions" about an account that
    does not exist, and the administrator who mistyped an id would believe it.
    """
    with pytest.raises(UserNotFoundError):
        auth_service.list_sessions(999)


def test_revoking_one_session_leaves_the_others_alone(auth_service, generate_user) -> None:
    user = generate_user()
    first_token, _ = auth_service.login("maria@arquivo.org", PASSWORD)
    second_token, _ = auth_service.login("maria@arquivo.org", PASSWORD)

    auth_service.revoke_session(user.user_id, auth_service.list_sessions(user.user_id)[0].session_id)

    still_live = [auth_service.resolve_session(token) is not None for token in (first_token, second_token)]
    assert still_live.count(True) == 1


def test_a_session_of_another_account_cannot_be_revoked_through_it(auth_service, generate_user) -> None:
    """
    The id alone must not be enough.

    Both sides of the refusal are asserted: the call raises *and* the session is still live — an
    implementation that revoked first and validated later would pass the first assertion alone.
    """
    owner = generate_user(email="maria@arquivo.org")
    other = generate_user(email="ana@arquivo.org")
    token, _ = auth_service.login("maria@arquivo.org", PASSWORD)
    session = auth_service.list_sessions(owner.user_id)[0]

    with pytest.raises(SessionNotFoundError):
        auth_service.revoke_session(other.user_id, session.session_id)

    assert auth_service.resolve_session(token) is not None


def test_revoking_an_unknown_session_is_a_not_found(auth_service, generate_user) -> None:
    user = generate_user()

    with pytest.raises(SessionNotFoundError):
        auth_service.revoke_session(user.user_id, 999)


def test_revoking_every_session_ends_all_of_them(auth_service, generate_user) -> None:
    """The "sign out everywhere" of a lost laptop, and it reports how many it ended."""
    user = generate_user()
    tokens = [auth_service.login("maria@arquivo.org", PASSWORD)[0] for _ in range(3)]

    ended = auth_service.revoke_all_sessions(user.user_id)

    assert ended == 3
    assert auth_service.list_sessions(user.user_id) == []
    assert all(auth_service.resolve_session(token) is None for token in tokens)


# ==========================================
# THE LOCKOUT (B9.3)
# ==========================================


def test_failed_attempts_are_counted_and_lock_the_account(auth_service, generate_user, monkeypatch) -> None:
    """
    The count reaches the threshold and the account locks — written through the recorder's own
    session, which is the whole reason the column can hold a fact the request transaction discards.
    """
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 3)
    user = generate_user()

    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate("maria@arquivo.org", "a senha errada")

    assert user.failed_attempts == 3
    assert user.locked_until is not None


def test_a_correct_password_on_a_locked_account_is_told_the_lockout(auth_service, generate_user, monkeypatch) -> None:
    """
    The one branch allowed to name the reason: the password verified, so the reader already knew it.

    An attacker guessing keeps getting the generic sentence — the answer that would enumerate a
    locked account is never reached without the password.
    """
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)
    generate_user()

    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate("maria@arquivo.org", "a senha errada")

    with pytest.raises(AccountLockedError):
        auth_service.authenticate("maria@arquivo.org", PASSWORD)
    with pytest.raises(InvalidCredentialsError):
        auth_service.authenticate("maria@arquivo.org", "a senha errada")


def test_a_wrong_password_while_locked_does_not_keep_counting(auth_service, generate_user, monkeypatch) -> None:
    """The account is already locked; growing the count further would only punish the owner."""
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)
    user = generate_user()
    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate("maria@arquivo.org", "a senha errada")
    locked_until = user.locked_until

    with pytest.raises(InvalidCredentialsError):
        auth_service.authenticate("maria@arquivo.org", "outra senha errada")

    assert user.failed_attempts == 2
    assert user.locked_until == locked_until


def test_the_lockout_doubles_with_each_further_one(auth_service, generate_user, monkeypatch) -> None:
    """
    The backoff rides on the count: the second lockout is twice the first, up to the ceiling.

    An expired lock is simulated instead of waiting for it, which also pins that the lock lifts by
    itself — nothing has to clear the column for the account to be usable again.
    """
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "AUTH_LOGIN_LOCKOUT_MINUTES", 10)
    monkeypatch.setattr(settings, "AUTH_LOGIN_LOCKOUT_MAX_MINUTES", 60)
    user = generate_user()

    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate("maria@arquivo.org", "a senha errada")
    first = user.locked_until
    assert first is not None
    assert 9 <= (first - datetime.now(UTC)).total_seconds() / 60 <= 11

    # The lock expires: the account is usable again, and the count keeps going from where it stopped.
    user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate("maria@arquivo.org", "a senha errada")

    second = user.locked_until
    assert second is not None
    assert 19 <= (second - datetime.now(UTC)).total_seconds() / 60 <= 21


def test_a_successful_login_clears_the_failed_attempts(auth_service, generate_user, monkeypatch) -> None:
    """The count is "since the last success", so a person who remembers the password starts clean."""
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_ATTEMPTS", 5)
    user = generate_user()
    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate("maria@arquivo.org", "a senha errada")

    auth_service.login("maria@arquivo.org", PASSWORD)

    assert user.failed_attempts == 0
    assert user.locked_until is None
