"""the ledger records the cancellation request, its author and the CANCELLED outcome

ADR 0014 decision 9 reserved the cancellation for #72 and fixed its vocabulary: the request is a
timestamped flag, not a status that frees the slot, because releasing the slot while the worker is
still writing would let a second run overlap it. ``cancel_requested_at`` is that flag; a ``QUEUED``
row no runner has claimed is closed ``CANCELLED`` by the API at once, and a claimed row keeps
``QUEUED``/``RUNNING`` until the worker honours the request at a batch boundary.

``cancel_requested_by`` and ``cancel_requested_by_user_id`` mirror ``requested_by``: starting and
stopping are two decisions, the second may be taken by another person, and the ledger has to say
who took it. The account link is ``SET NULL`` like every other authorship column, so a deactivated
(or removed) account keeps its name on the decision.

``worker_run_status`` gains ``CANCELLED``, additive: ``INTERRUPTED`` remains the sweep's verdict on a
runner that disappeared, and the two are deliberately different facts.

The migration is additive. Existing rows read ``cancel_requested_at = NULL`` (nobody asked) and keep
their status; the enum value is kept on downgrade, because PostgreSQL cannot remove a value from an
enum without recreating the type — the same decision ``b7e4c2a9f1d0`` took for ``SCHEDULE``.

Revision ID: d72c0a4b1e9f
Revises: b7e4c2a9f1d0
Create Date: 2026-10-25 14:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "d72c0a4b1e9f"
down_revision: str | Sequence[str] | None = "b7e4c2a9f1d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The author link's name, spelled the way every authorship column of this schema names it, so the
#: downgrade drops exactly what the upgrade created.
CANCEL_AUTHOR_FK = "fk_archive_worker_runs_cancel_requested_by_user_id"


def upgrade() -> None:
    """Adds the request, its author and the ``CANCELLED`` status."""
    # ``ALTER TYPE ... ADD VALUE`` cannot run inside the transaction a migration normally opens.
    # Committing first is what PostgreSQL requires; ``IF NOT EXISTS`` keeps a replay idempotent.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE worker_run_status ADD VALUE IF NOT EXISTS 'CANCELLED'")

    op.add_column("archive_worker_runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("archive_worker_runs", sa.Column("cancel_requested_by", sa.String(length=120), nullable=True))
    op.add_column("archive_worker_runs", sa.Column("cancel_requested_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        CANCEL_AUTHOR_FK,
        "archive_worker_runs",
        "auth_users",
        ["cancel_requested_by_user_id"],
        ["user_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """
    Drops the columns; the enum value is deliberately **kept**.

    PostgreSQL cannot remove a value from an enum type, and recreating the type would mean rewriting
    every column that uses it — a destructive dance for a label that is inert once no code writes it.
    A leftover value in an enum is harmless; a downgrade that fails on a populated table is not.
    """
    op.drop_constraint(CANCEL_AUTHOR_FK, "archive_worker_runs", type_="foreignkey")
    op.drop_column("archive_worker_runs", "cancel_requested_by_user_id")
    op.drop_column("archive_worker_runs", "cancel_requested_by")
    op.drop_column("archive_worker_runs", "cancel_requested_at")
