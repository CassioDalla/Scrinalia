"""Business refusals of the identity domain.

Same shape as ``domains/archive/exceptions.py``: the base class lives in ``core`` so one handler in
the HTTP layer catches every domain's refusals, and each class documents the status it should become.
"""

from scrinalia.core.exceptions import DomainException


class UserNotFoundError(DomainException):
    """Raised when an account named by an administrative operation does not exist."""

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class SessionNotFoundError(DomainException):
    """Raised when a session named by an administrative operation does not exist.

    Also the answer when the session exists but belongs to another account: from the screen's side
    the two are the same fact — there is no live session of *this* account with that id — and
    answering differently would let an administrator enumerate the sessions of an account they were
    not looking at.
    """

    # Ideal translation in Litestar: HTTP 404 (Not Found)
    pass


class DuplicateUserEmailError(DomainException):
    """Raised when an account would carry an address that is already taken."""

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass


class InvalidCredentialsError(DomainException):
    """Raised when a login cannot be granted.

    Deliberately **one** error for three different situations — unknown address, wrong password and
    deactivated account — with one sentence. Telling them apart is a user-enumeration oracle, and the
    person who needs the distinction (the administrator) has the account list to consult.
    """

    # Ideal translation in Litestar: HTTP 401 (Unauthorized)
    pass


class InvalidCurrentPasswordError(DomainException):
    """Raised when the current password given while changing it does not match."""

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass


class WeakPasswordError(DomainException):
    """Raised when a password is shorter than the policy or equal to the account's own address."""

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass


class InvalidEmailError(DomainException):
    """Raised when an address is not usable as an account identifier."""

    # Ideal translation in Litestar: HTTP 422 (Unprocessable Entity)
    pass


class LastAdminError(DomainException):
    """Raised when an operation would leave the installation with no active administrator.

    The only lockout this system cannot recover from through the UI: with every admin demoted or
    deactivated, nobody can create the next account, and the way back in is the CLI on the host.
    The rule is enforced in the service, so the CLI and the screen inherit the same one.
    """

    # Ideal translation in Litestar: HTTP 409 (Conflict)
    pass
