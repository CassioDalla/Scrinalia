"""Accounts as the API reads and writes them.

The password fields carry **no** ``min_length`` on purpose. The policy is a setting
(``AUTH_PASSWORD_MIN_LENGTH``) and it is enforced in the domain, which is the one place both callers
share — the HTTP body and the CLI. A second bound here would be a second definition, and the two
would disagree the moment an institution raises the minimum.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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

    model_config = ConfigDict(from_attributes=True)


class CreateUserCommand(BaseModel):
    """Creates an account. The password is hashed before it reaches the row."""

    email: str = Field(min_length=3, max_length=320, description="Identificador da conta; normalizado para minúsculas.")
    name: str = Field(min_length=1, max_length=120, description="Como o nome aparece nos ledgers e na tela.")
    role: Role = Field(description="O que a conta pode fazer além de ler.")
    password: str = Field(min_length=1, description="Senha inicial; a política é verificada no domínio.")


class UpdateUserCommand(BaseModel):
    """Partial update of an account. Everything is optional; nothing is required to change."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


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
