"""Credentials: how an e-mail identifies an account and how a password proves it.

Argon2id is the only KDF here, and its parameters are explicit rather than "whatever the library
defaults to": the cost of a password hash is a security parameter, and it has to be readable in the
code that chooses it. They live in ``Settings`` because a test suite must be able to lower the memory
cost instead of paying ~60 ms per login. Changing them does **not** invalidate existing hashes — the
parameters travel inside the hash string, so old hashes keep verifying and are upgraded on the next
successful login (``needs_rehash``).

Two rules that are easy to get wrong, and are the reason this module exists:

* verification **always** runs, even when the e-mail matches no account (``verify_decoy``). Returning
  early makes an unknown account answer in microseconds and a known one in tens of milliseconds, and
  that difference is a user-enumeration oracle which no amount of "invalid credentials" wording hides.
* the policy is checked here and not only in the request schema, because the CLI creates accounts
  without going through an HTTP body — and a rule that only exists at the boundary is not a rule.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from scrinalia.core.config import get_settings

from ..exceptions import InvalidEmailError, WeakPasswordError

#: Deliberately loose. The point is to catch a typo and a stray space, not to adjudicate RFC 5322:
#: an address that this regex accepts and a mail server would refuse is a problem nobody here has,
#: while a valid address this regex refused would lock an archivist out of their own installation.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    """
    The one spelling of an address the system stores and looks up.

    Lowercased and trimmed, because ``Maria@arquivo.org`` and ``maria@arquivo.org`` are the same
    person: without this the unique index would happily hold both and the archivist would have two
    accounts, one of which they cannot log into with the password they think they set.
    """
    normalized = email.strip().lower()
    if not _EMAIL.match(normalized):
        raise InvalidEmailError("Informe um e-mail válido.")
    return normalized


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    """One hasher per process, built from the settings so the cost is configuration and not a literal."""
    current = get_settings()
    return PasswordHasher(
        time_cost=current.AUTH_PASSWORD_TIME_COST,
        memory_cost=current.AUTH_PASSWORD_MEMORY_KIB,
        parallelism=current.AUTH_PASSWORD_PARALLELISM,
    )


@lru_cache(maxsize=1)
def _decoy_hash() -> str:
    """
    A hash to verify against when the account does not exist.

    Built once, lazily, from a random secret that is thrown away: it exists only so that
    ``verify_decoy`` pays the same cost as a real verification.
    """
    return _hasher().hash(secrets.token_urlsafe(32))


def check_password_policy(password: str, *, email: str | None = None) -> None:
    """Refuses a password that is too short or is the account's own address."""
    minimum = get_settings().AUTH_PASSWORD_MIN_LENGTH
    if len(password) < minimum:
        raise WeakPasswordError(f"A senha precisa ter ao menos {minimum} caracteres.")
    if email is not None and password.strip().lower() == normalize_email(email):
        raise WeakPasswordError("A senha não pode ser o próprio e-mail.")


def hash_password(password: str) -> str:
    """Hashes a password with argon2id. The parameters travel inside the returned string."""
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    Whether ``password`` matches the stored hash.

    A malformed or truncated stored hash is a **refusal**, not an exception: the row is unusable and
    the answer the client deserves is the same one a wrong password gets. ``UnicodeEncodeError`` is in
    the list because argon2 encodes the *hash* as ASCII before parsing it and raises that — not
    ``InvalidHashError`` — for a value with a non-ASCII byte, which the ``Text`` column can hold.
    """
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, UnicodeEncodeError):
        return False


def verify_decoy(password: str) -> None:
    """Spends the time of a real verification when the account does not exist. Always fails."""
    with contextlib.suppress(VerifyMismatchError, VerificationError, InvalidHashError):
        _hasher().verify(_decoy_hash(), password)


def needs_rehash(password_hash: str) -> bool:
    """Whether the stored hash used weaker parameters than the ones configured today."""
    try:
        return _hasher().check_needs_rehash(password_hash)
    except (InvalidHashError, UnicodeEncodeError):
        # An unparseable hash cannot be upgraded; the login that would have upgraded it will fail
        # verification first, and answering ``True`` here would invite a rehash of garbage.
        return False


#: Entropy of a session token. 32 bytes is the size of the random part of the cookie, and it is the
#: only thing standing between a session and a guess: 256 bits, so no rate limit is doing the work.
SESSION_TOKEN_BYTES = 32


def generate_session_token() -> str:
    """A fresh session token: URL-safe, because it travels in a cookie header."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """
    What the database stores instead of the token.

    A plain SHA-256 and not argon2, deliberately: this is a **high-entropy random** value, not a
    password, so there is nothing to slow down — a brute force over 256 bits is not a threat that a
    memory-hard function changes. What matters is that the stored form cannot be replayed as a cookie,
    and a one-way digest gives exactly that. It is also the lookup key, so it has to be deterministic.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
