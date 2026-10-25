"""the run ledger becomes a queue: the request, the runner and its lease

ADR 0014 moves the executor out of the API. A ``QUEUED`` row is the work item now, so it has to
carry the request it was asked for (``request``) and the runner that claimed it (``runner_id``,
``heartbeat_at``, ``lease_expires_at``). ``archive_worker_runners`` is the registry the panel reads
to answer "is a runner alive, and can it run this worker?".

The three partial indexes are the protocol's readers: the claim reads ``QUEUED`` rows by
``queued_at``, the sweeper reads ``RUNNING`` rows by ``lease_expires_at``, and the heartbeat updates
the runs of one ``runner_id``.

The migration also closes the rows the in-process executor left in flight. That is a one-time
transition, not a cleanup: before this release an active row could only belong to an API process,
and after it the only thing that repairs an orphan is a lease. Leaving old rows ``QUEUED`` would
block their worker forever. The downgrade drops the schema; it does not resurrect the interrupted
rows.

Revision ID: a842f9efad08
Revises: efe037349552
Create Date: 2026-10-25 01:46:51.307081

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "a842f9efad08"
down_revision: str | Sequence[str] | None = "efe037349552"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Adds the queue/lease columns and the runner registry, then closes the old active rows."""
    op.create_table(
        "archive_worker_runners",
        sa.Column("runner_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=True),
        sa.Column(
            "capabilities", postgresql.ARRAY(sa.String()), server_default=sa.text("'{}'::text[]"), nullable=False
        ),
        sa.Column("concurrency", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("heartbeat_seconds", sa.Integer(), server_default=sa.text("15"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("runner_id"),
    )
    op.create_index("ix_worker_runner_last_heartbeat", "archive_worker_runners", ["last_heartbeat_at"], unique=False)

    op.add_column(
        "archive_worker_runs",
        sa.Column(
            "request",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("archive_worker_runs", sa.Column("runner_id", sa.String(length=120), nullable=True))
    op.add_column("archive_worker_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("archive_worker_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))

    # The one-time transition: the old executor is gone, so every active row belongs to a process
    # that no longer exists. Closing them releases the partial unique index and gives the panel an
    # honest outcome instead of a run that never finishes.
    op.execute(
        sa.text(
            "UPDATE archive_worker_runs "
            "SET status = 'INTERRUPTED', "
            "finished_at = now(), "
            "duration_ms = CASE WHEN started_at IS NULL THEN NULL "
            "ELSE CAST(EXTRACT(EPOCH FROM (now() - started_at)) * 1000 AS INTEGER) END, "
            "error = 'A execução anterior à mudança para o runner externo foi interrompida.' "
            "WHERE status IN ('QUEUED', 'RUNNING')"
        )
    )

    op.create_index(
        "ix_worker_run_lease",
        "archive_worker_runs",
        ["lease_expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.create_index(
        "ix_worker_run_queue",
        "archive_worker_runs",
        ["queued_at"],
        unique=False,
        postgresql_where=sa.text("status = 'QUEUED'"),
    )
    op.create_index(
        "ix_worker_run_runner",
        "archive_worker_runs",
        ["runner_id"],
        unique=False,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    """Drops the queue columns and the registry; the interrupted rows stay interrupted."""
    op.drop_index(
        "ix_worker_run_runner", table_name="archive_worker_runs", postgresql_where=sa.text("status = 'RUNNING'")
    )
    op.drop_index(
        "ix_worker_run_queue", table_name="archive_worker_runs", postgresql_where=sa.text("status = 'QUEUED'")
    )
    op.drop_index(
        "ix_worker_run_lease", table_name="archive_worker_runs", postgresql_where=sa.text("status = 'RUNNING'")
    )
    op.drop_column("archive_worker_runs", "lease_expires_at")
    op.drop_column("archive_worker_runs", "heartbeat_at")
    op.drop_column("archive_worker_runs", "runner_id")
    op.drop_column("archive_worker_runs", "request")

    op.drop_index("ix_worker_runner_last_heartbeat", table_name="archive_worker_runners")
    op.drop_table("archive_worker_runners")
