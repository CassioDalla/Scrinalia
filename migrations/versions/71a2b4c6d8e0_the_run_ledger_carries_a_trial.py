"""the run ledger carries a trial and the metrics it measured

A trial (ADR 0018) is a comparison of two or more configurations of one worker executed as **one**
row: it runs over one fixed sample, writes no archival content, and stores its per-configuration
metrics in ``trial_result``. ``trial`` is the boolean that distinguishes it from a production run in
the operations panel; ``trigger`` keeps meaning *who* asked (the trial is enqueued by the panel, so
``API``), because the trigger and the kind of execution are two different facts.

Both columns are additive. Existing rows read ``trial = false`` and ``trial_result = NULL``, which is
exactly what a production run is; the server default stays so a writer that omits the flag cannot
create a row the panel would have to guess about.

Revision ID: 71a2b4c6d8e0
Revises: 44a1b2c3d4e5
Create Date: 2026-10-25 18:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "71a2b4c6d8e0"
down_revision: str | Sequence[str] | None = "44a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Adds the trial flag and the result the comparison measured."""
    op.add_column(
        "archive_worker_runs",
        sa.Column("trial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "archive_worker_runs",
        sa.Column("trial_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Drops both columns; a trial's evidence is not part of the collection and a run is not undone."""
    op.drop_column("archive_worker_runs", "trial_result")
    op.drop_column("archive_worker_runs", "trial")
