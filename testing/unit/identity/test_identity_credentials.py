"""The credential rules: hashing, the policy, and the two things that must not leak.

The tests that matter here are the negative ones. "A right password verifies" is true of every
plausible implementation, including the ones that answer a wrong password with a different *timing*
for an account that exists and one that does not.
"""

import pytest
from argon2 import PasswordHasher

from scrinalia.domains.identity.domain.credentials import (
    SESSION_TOKEN_BYTES,
    check_password_policy,
    generate_session_token,
    hash_password,
    hash_session_token,
    needs_rehash,
    normalize_email,
    verify_decoy,
    verify_password,
)
from scrinalia.domains.identity.exceptions import InvalidEmailError, WeakPasswordError

#: A password above the default policy, so a test that is not about the policy never trips it.
PASSWORD = "uma senha bem longa"


# ==========================================
# HASHING
# ==========================================


def test_the_hash_is_argon2id_and_carries_its_parameters() -> None:
    """The algorithm is asserted by name: a silent fallback to a weaker KDF would still verify."""
    assert hash_password(PASSWORD).startswith("$argon2id$")


def test_the_same_password_hashes_differently_every_time() -> None:
    """Salted, so two accounts with the same password do not share a hash."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verification_accepts_the_password_and_refuses_another() -> None:
    stored = hash_password(PASSWORD)
    assert verify_password(PASSWORD, stored) is True
    assert verify_password("outra senha qualquer", stored) is False


def test_a_malformed_stored_hash_is_a_refusal_and_not_an_exception() -> None:
    """
    A truncated column is a row nobody can use; the answer is the one a wrong password gets.

    The non-ASCII case is not hypothetical decoration: argon2 encodes the *stored* value as ASCII
    before parsing it and raises ``UnicodeEncodeError`` — not ``InvalidHashError`` — for a byte it
    cannot encode, and ``password_hash`` is a ``Text`` column that can hold one.
    """
    assert verify_password(PASSWORD, "não é um hash") is False
    assert verify_password(PASSWORD, "$argon2id$v=19$m=65536") is False
    assert verify_password(PASSWORD, "") is False


def test_a_hash_made_with_weaker_parameters_asks_to_be_rehashed() -> None:
    """
    This is what upgrades an installation's hashes without a migration.

    The weak hash is built here with explicit parameters instead of by lowering the settings, so the
    test states the rule ("the parameters are compared") and not an artifact of configuration.
    """
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)

    assert verify_password(PASSWORD, weak) is True
    assert needs_rehash(weak) is True
    assert needs_rehash(hash_password(PASSWORD)) is False


def test_needs_rehash_does_not_raise_on_an_unparseable_hash() -> None:
    assert needs_rehash("não é um hash") is False
    assert needs_rehash("$argon2id$v=19$m=65536") is False


def test_the_decoy_verification_fails_silently() -> None:
    """It exists to spend time, not to answer: raising here would turn an unknown account into a 500."""
    assert verify_decoy(PASSWORD) is None


# ==========================================
# THE PASSWORD POLICY
# ==========================================


def test_a_short_password_is_refused() -> None:
    with pytest.raises(WeakPasswordError):
        check_password_policy("curta")


def test_a_password_equal_to_the_address_is_refused() -> None:
    """The one guess everybody makes first, and the one an e-mail list makes easy."""
    with pytest.raises(WeakPasswordError):
        check_password_policy("maria@arquivo.org", email="maria@arquivo.org")


def test_an_acceptable_password_passes_the_policy() -> None:
    assert check_password_policy(PASSWORD, email="maria@arquivo.org") is None


# ==========================================
# THE ADDRESS
# ==========================================


def test_the_address_is_normalised_to_one_spelling() -> None:
    """One account per person, not one per spelling: the unique index depends on this."""
    assert normalize_email("  Maria@Arquivo.ORG ") == "maria@arquivo.org"


@pytest.mark.parametrize("value", ["sem-arroba", "@arquivo.org", "maria@", "maria arquivo@x.org", ""])
def test_an_unusable_address_is_refused(value: str) -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email(value)


# ==========================================
# THE SESSION TOKEN
# ==========================================


def test_a_session_token_is_long_enough_to_not_be_guessed() -> None:
    """The entropy is the whole defence: no rate limit is doing this work."""
    token = generate_session_token()
    assert len(token) >= SESSION_TOKEN_BYTES
    assert generate_session_token() != token


def test_only_the_digest_of_a_token_is_stored() -> None:
    token = generate_session_token()
    digest = hash_session_token(token)

    assert digest != token
    assert len(digest) == 64
    # Deterministic, because it is the lookup key of every authenticated request.
    assert hash_session_token(token) == digest
