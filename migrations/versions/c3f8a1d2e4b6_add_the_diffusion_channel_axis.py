"""Add the diffusion channel axis to the run ledger

The diffusion export reuses ``archive_worker_runs`` instead of opening a second ledger (ADR 0023
§7): the claim, the lease, the cancellation, the retry, the failure fingerprint and the panel's
"in flight" answer are already there, and a second ledger would duplicate all of them. What the
ledger did not have is the axis: a run of the ``diffusion`` worker names the **channel** it writes,
the way a run of ``ingestion`` names the origin it reads.

* ``archive_worker_runs.channel_code`` — nullable and indexed, like ``origin_code`` beside it. The
  archive workers keep both NULL; ``ingestion`` sets the origin and ``diffusion`` sets the channel.
* ``uq_worker_run_active`` — the concurrency guard becomes
  ``(worker_name, COALESCE(origin_code, ''), COALESCE(channel_code, ''))`` with the same partial
  predicate. The archive workers keep their one-slot-per-worker guarantee (both columns coalesce to
  one value), while each origin and each channel gets a slot of its own: two channels export at the
  same time, and a second run of one channel waits.

No data migration: every row that existed was written by a worker whose axis is the origin or by an
archive worker, so the new column is NULL for all of them and the invariant holds without a backfill.

Revision ID: c3f8a1d2e4b6
Revises: 0b1c2d3e4f5a
Create Date: 2026-10-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "c3f8a1d2e4b6"
down_revision: str | Sequence[str] | None = "0b1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The partial predicate of the guard, spelled as the model and the two migrations before this one
#: spell it. It lives here rather than importing ``ACTIVE_RUN_PREDICATE`` because a migration is a
#: snapshot of the schema at this revision and must not follow the code when the constant changes.
ACTIVE_RUN_PREDICATE = "status IN ('QUEUED', 'RUNNING')"


def upgrade() -> None:
    op.add_column("archive_worker_runs", sa.Column("channel_code", sa.String(length=50), nullable=True))
    op.create_index("ix_archive_worker_runs_channel_code", "archive_worker_runs", ["channel_code"])

    op.drop_index("uq_worker_run_active", table_name="archive_worker_runs")
    op.create_index(
        "uq_worker_run_active",
        "archive_worker_runs",
        ["worker_name", sa.text("COALESCE(origin_code, '')"), sa.text("COALESCE(channel_code, '')")],
        unique=True,
        postgresql_where=sa.text(ACTIVE_RUN_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("uq_worker_run_active", table_name="archive_worker_runs")
    op.create_index(
        "uq_worker_run_active",
        "archive_worker_runs",
        ["worker_name", sa.text("COALESCE(origin_code, '')")],
        unique=True,
        postgresql_where=sa.text(ACTIVE_RUN_PREDICATE),
    )

    op.drop_index("ix_archive_worker_runs_channel_code", table_name="archive_worker_runs")
    op.drop_column("archive_worker_runs", "channel_code")
