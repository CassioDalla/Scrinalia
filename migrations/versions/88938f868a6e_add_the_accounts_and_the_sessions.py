"""add the accounts and the sessions

The first tables whose subject is the *installation* rather than the collection: ``auth_users`` (who
may write, and with which role) and ``auth_sessions`` (one sign-in, revocable).

Three decisions live in the schema and not in the code:

* the session row stores the **SHA-256 of the token**, never the token. A dump of this table cannot be
  replayed as a cookie, and ``revoked_at`` is what makes "sign out everywhere" real — a signed
  stateless cookie can only be waited out.
* there is no delete path for an account: it is deactivated. Every ledger in the archive records who
  decided what, and the ``changed_by_user_id`` foreign key is ``SET NULL``; removing the account would
  erase the *who* of decisions that still stand. ``is_active`` takes the access away and keeps the name
  readable, which are two different things an archive needs.
* ``failed_attempts``/``locked_until`` ship with the table even though nothing writes them yet: the
  login path that will write them cannot use the request transaction — a failed login raises, and
  ``provide_unit_of_work`` rolls back on the way out, so a counter incremented there would be erased by
  the very failure it counts. It needs its own committed session, exactly like ``archive_worker_runs``.
  Having the columns from the start means that work is code, not a second migration.

Revision ID: 88938f868a6e
Revises: b3d6f1a2c4e7
Create Date: 2026-10-07 19:26:15.161280

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "88938f868a6e"
down_revision: str | Sequence[str] | None = "b3d6f1a2c4e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the accounts and the sessions."""
    op.create_table(
        "auth_users",
        sa.Column("user_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", "CURATOR", "VIEWER", name="user_role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("must_change_password", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("session_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_expires_at"), "auth_sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    """Drop both tables, and the role type with them.

    ``drop_table`` does not remove a PostgreSQL enum, so the type is dropped explicitly — otherwise a
    re-upgrade would fail on a type that already exists.
    """
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_expires_at"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("auth_users")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
