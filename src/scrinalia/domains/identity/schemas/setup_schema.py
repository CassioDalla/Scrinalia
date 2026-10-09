"""What the first-run screen sends and reads.

Two models and deliberately no ``role`` field: the installation's first account administers, and a
client that could ask for another role here would be choosing what the deployment's only account is
allowed to do. The password carries no ``min_length`` for the same reason as everywhere else — the
policy is a setting enforced in the domain, which is the one place the API and the CLI share.
"""

from pydantic import BaseModel, Field


class SetupStatusResponse(BaseModel):
    """
    Whether this installation still has to be brought to life.

    ``True`` means ``auth_users`` is empty, and nothing else is said: an installation with no accounts
    has no secret to protect, and the screen has to decide *before* it holds a session (ADR 0011).
    """

    needs_setup: bool


class SetupFirstAdminCommand(BaseModel):
    """The account the first-run screen creates. It always becomes an ``ADMIN``."""

    email: str = Field(min_length=3, max_length=320, description="Identificador da conta; normalizado para minúsculas.")
    name: str = Field(min_length=1, max_length=120, description="Como o nome aparece nos ledgers e na tela.")
    password: str = Field(
        min_length=1, description="A senha escolhida pela pessoa; a política é verificada no domínio."
    )
