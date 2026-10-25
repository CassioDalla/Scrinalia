"""record the options the run used

``archive_worker_runs`` carried the engine's resolved configuration (``config``) and no record of
the **worker's own** options, so "which columns did run #N read?" had no answer: the columns live
inside the producer fingerprint the stamp hashes, and a hash cannot be read back (issue #120).

The row now records them, resolved when the run starts — the default of a column list lives in the
worker's own runner dataclass, so only the worker can say which text it read. Additive and safe for
the rows that already exist: they keep the empty default, and the panel says "não registradas".

Revision ID: efe037349552
Revises: c4a9e1f7b2d6
Create Date: 2026-10-24 20:37:30.077443

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "efe037349552"
down_revision: str | Sequence[str] | None = "c4a9e1f7b2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Adds the effective worker options to the execution ledger."""
    op.add_column(
        "archive_worker_runs",
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drops the column; the engine configuration beside it keeps the row readable."""
    op.drop_column("archive_worker_runs", "options")
