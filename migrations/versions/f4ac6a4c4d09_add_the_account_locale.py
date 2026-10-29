"""add the account locale

Revision ID: f4ac6a4c4d09
Revises: f1090f825a94
Create Date: 2026-10-27 22:18:10.097623

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4ac6a4c4d09"
down_revision: str | Sequence[str] | None = "f1090f825a94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the interface language the account chose; NULL means automatic (ADR 0020 §3)."""
    op.add_column("auth_users", sa.Column("locale", sa.String(length=8), nullable=True))
    op.create_check_constraint(
        "chk_auth_users_locale",
        "auth_users",
        "locale IS NULL OR locale IN ('pt-BR', 'en')",
    )


def downgrade() -> None:
    """Drop the account's language: the interface falls back to the browser and the default."""
    op.drop_constraint("chk_auth_users_locale", "auth_users", type_="check")
    op.drop_column("auth_users", "locale")
