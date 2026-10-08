"""Accounts as the API reads and writes them.

The password fields carry **no** ``min_length`` on purpose. The policy is a setting
(``AUTH_PASSWORD_MIN_LENGTH``) and it is enforced in the domain, which is the one place both callers
share — the HTTP body and the CLI. A second bound here would be a second definition, and the two
would disagree the moment an institution raises the minimum.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from scrinalia.domains.identity.domain.permissions import Role


class AuthUserDTO(BaseModel):
    """
    One account, as every screen and the session itself read it.

    There is deliberately no ``password_hash`` and no session token: this is the model that reaches a
    client, and the hash is not a field to forget to exclude — it is absent.
    """

    user_id: int
    email: str
    name: str
    role: Role
    is_active: bool
    #: True while the account still carries the temporary password the CLI printed.
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    #: How many sign-ins failed since the last success. Surfaced so the accounts screen can show a
    #: lockout instead of leaving the administrator to guess why somebody cannot get in; it is the
    #: same number the lockout is computed from, never a second counter.
    failed_attempts: int = 0
    #: When the lockout lifts, or ``None``. A value in the past is a lockout that has already served
    #: its time — the next failure starts the count again from where it stopped.
    locked_until: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_locked(self) -> bool:
        """
        Whether the lockout is in force **now**.

        Computed on the server and not in the browser: "now" is the server's clock, and a screen that
        compared timestamps itself would need an impure read during render to decide it — which is
        exactly the kind of thing that makes a React component stop being reproducible.
        """
        return self.locked_until is not None and self.locked_until > datetime.now(UTC)


class CreateUserCommand(BaseModel):
    """Creates an account. The password is hashed before it reaches the row."""

    email: str = Field(min_length=3, max_length=320, description="Identificador da conta; normalizado para minúsculas.")
    name: str = Field(min_length=1, max_length=120, description="Como o nome aparece nos ledgers e na tela.")
    #: No ``Field(description=...)`` here on purpose: ``Role`` is a shared enum, and Litestar applies
    #: a field's kwargs to the enum's **component**, so the description would become the type's for
    #: the whole document — and which field wins depends on the walk order, and therefore on
    #: ``PYTHONHASHSEED``. The description of the type is its docstring; document it there.
    role: Role
    password: str = Field(min_length=1, description="Senha inicial; a política é verificada no domínio.")


class UpdateUserCommand(BaseModel):
    """Partial update of an account. Everything is optional; nothing is required to change."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


class AuthSessionDTO(BaseModel):
    """
    One live sign-in, as the accounts screen reads it.

    There is no token and no token hash: the row is identified by ``session_id``, which is enough to
    revoke it and useless for impersonating it. ``user_agent``/``ip_address`` are what let somebody
    recognise "that one is not me" — they are free-form context written at sign-in and never trusted.
    """

    session_id: int
    user_agent: str | None = None
    ip_address: str | None = None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    #: Whether this is the session making the request. Set by the controller from the cookie, never
    #: stored: it is a fact about *this* request, not about the row.
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True)


class SetPasswordCommand(BaseModel):
    """An administrator (or the CLI) sets a new password without knowing the old one."""

    password: str = Field(min_length=1, description="Nova senha; a política é verificada no domínio.")
    #: Whether the person must replace it at the next sign-in. The CLI's bootstrap sets it, because
    #: the password it prints to the terminal was chosen by nobody who will use it.
    must_change: bool = True


class ChangePasswordCommand(BaseModel):
    """The account changes its own password, proving it knows the current one."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
