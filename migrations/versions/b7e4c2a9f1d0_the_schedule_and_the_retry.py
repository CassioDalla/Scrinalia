"""the schedule and the retry: one cron row per worker, one ledger row per attempt

ADR 0015 gives the worker a durable agenda and #43 implements it. ``archive_worker_schedules`` holds
one row per worker: a five-field cron, an explicit IANA timezone, the validated request it runs,
whether it is enabled and the ``next_run_at`` the scheduler checks. It is one row per worker because
the queue is one slot per worker (``uq_worker_run_active``): two schedules for the same worker would
only collide and be skipped.

The ledger gains the retry's three columns: ``attempt`` (1 for a run asked once, N for the N-th
attempt of a scheduled run), ``retry_of`` (the row this one retries) and ``not_before`` (the earliest
moment the claim may take it, so a retry waits out its backoff without a second queue). The retry is
created only after the previous row is terminal, so the partial unique index is never violated.

``worker_run_trigger`` gains ``SCHEDULE``: the ledger keeps saying who asked — the command line, the
panel or the schedule — and the retry policy only ever looks at the third.

The migration is additive. Existing rows read ``attempt=1``, ``not_before=NULL`` and
``retry_of=NULL``: before this change a run had exactly one attempt.

Revision ID: b7e4c2a9f1d0
Revises: a842f9efad08
Create Date: 2026-10-25 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "b7e4c2a9f1d0"
down_revision: str | Sequence[str] | None = "a842f9efad08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Adds the schedule table, the retry columns and the ``SCHEDULE`` trigger."""
    # ``ALTER TYPE ... ADD VALUE`` cannot run inside the transaction a migration normally opens.
    # Committing first is what PostgreSQL requires; ``IF NOT EXISTS`` keeps a replay idempotent.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE worker_run_trigger ADD VALUE IF NOT EXISTS 'SCHEDULE'")

    op.create_table(
        "archive_worker_schedules",
        sa.Column("worker_name", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("cron", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "request",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_skipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("worker_name"),
    )
    op.create_index("ix_worker_schedule_next_run_at", "archive_worker_schedules", ["next_run_at"])

    op.add_column(
        "archive_worker_runs",
        sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("archive_worker_runs", sa.Column("retry_of", sa.Integer(), nullable=True))
    op.add_column("archive_worker_runs", sa.Column("not_before", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        None,
        "archive_worker_runs",
        "archive_worker_runs",
        ["retry_of"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_worker_run_retry_of", "archive_worker_runs", ["retry_of"])


def downgrade() -> None:
    """
    Drops the columns and the table; the enum value is deliberately **kept**.

    PostgreSQL cannot remove a value from an enum type, and recreating the type would mean rewriting
    every column that uses it — a destructive dance for a label that is inert once no code writes
    it. A leftover value in an enum is harmless; a downgrade that fails on a populated table is not.
    """
    op.drop_index("ix_worker_run_retry_of", table_name="archive_worker_runs")
    op.drop_constraint("archive_worker_runs_retry_of_fkey", "archive_worker_runs", type_="foreignkey")
    op.drop_column("archive_worker_runs", "not_before")
    op.drop_column("archive_worker_runs", "retry_of")
    op.drop_column("archive_worker_runs", "attempt")

    op.drop_index("ix_worker_schedule_next_run_at", table_name="archive_worker_schedules")
    op.drop_table("archive_worker_schedules")
