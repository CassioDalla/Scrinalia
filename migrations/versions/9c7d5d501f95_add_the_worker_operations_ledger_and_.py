"""add the worker operations ledger and settings

Three tables that make the operation of the AI workers observable and configurable:

* ``archive_worker_settings`` — the persisted default engine/preset/batch/options of a worker.
  ``NULL`` means "keep following the code", so a field nobody overrode still picks up a preset
  renamed in a later release.
* ``archive_worker_settings_revisions`` — the audit trail of every write, in the same spirit as
  ``archive_document_revisions``: the decision and the write are different facts.
* ``archive_worker_runs`` — one row per execution, written by the runner for both the CLI and the
  panel. ``uq_worker_run_active`` is the concurrency guard: a **partial unique index** on
  ``worker_name`` for the rows in flight, so a second run for the same worker is impossible across
  processes and across a reload. The guarantee had to live in the database — a process-local lock
  does not survive ``--reload``, and the API is the only thing that knows the run is in flight.

There is deliberately no foreign key to a worker table: workers are code, not rows, and a ledger
must keep reading after a worker is removed from the catalogue.

Revision ID: 9c7d5d501f95
Revises: e423cd04973a
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c7d5d501f95"
down_revision: str | None = "e423cd04973a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The two native enum types this revision owns. They are created implicitly by ``create_table``
#: and must be dropped explicitly: PostgreSQL does not drop a standalone type with its table, so
#: without this the downgrade would leave the type behind and the next upgrade would fail.
RUN_STATUS = postgresql.ENUM("QUEUED", "RUNNING", "SUCCESS", "FAILED", "INTERRUPTED", name="worker_run_status")
RUN_TRIGGER = postgresql.ENUM("CLI", "API", name="worker_run_trigger")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "archive_worker_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("worker_name", sa.String(length=50), nullable=False),
        sa.Column("status", RUN_STATUS, nullable=False),
        sa.Column("trigger", RUN_TRIGGER, nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=True),
        sa.Column("engine_name", sa.String(length=50), nullable=True),
        sa.Column("preset", sa.String(length=50), nullable=True),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_archive_worker_runs_status"), "archive_worker_runs", ["status"], unique=False)
    op.create_index(op.f("ix_archive_worker_runs_worker_name"), "archive_worker_runs", ["worker_name"], unique=False)
    op.create_index("ix_worker_run_queued_at", "archive_worker_runs", ["queued_at"], unique=False)
    op.create_index(
        "uq_worker_run_active",
        "archive_worker_runs",
        ["worker_name"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )

    op.create_table(
        "archive_worker_settings",
        sa.Column("worker_name", sa.String(length=50), nullable=False),
        sa.Column("engine_name", sa.String(length=50), nullable=True),
        sa.Column("preset", sa.String(length=50), nullable=True),
        sa.Column("db_batch_size", sa.Integer(), nullable=True),
        sa.Column(
            "options", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("worker_name"),
    )

    op.create_table(
        "archive_worker_settings_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("worker_name", sa.String(length=50), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changed_by", sa.String(length=120), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_archive_worker_settings_revisions_worker_name"),
        "archive_worker_settings_revisions",
        ["worker_name"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_archive_worker_settings_revisions_worker_name"), table_name="archive_worker_settings_revisions"
    )
    op.drop_table("archive_worker_settings_revisions")
    op.drop_table("archive_worker_settings")
    op.drop_index(
        "uq_worker_run_active",
        table_name="archive_worker_runs",
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )
    op.drop_index("ix_worker_run_queued_at", table_name="archive_worker_runs")
    op.drop_index(op.f("ix_archive_worker_runs_worker_name"), table_name="archive_worker_runs")
    op.drop_index(op.f("ix_archive_worker_runs_status"), table_name="archive_worker_runs")
    op.drop_table("archive_worker_runs")

    RUN_TRIGGER.drop(op.get_bind(), checkfirst=True)
    RUN_STATUS.drop(op.get_bind(), checkfirst=True)
