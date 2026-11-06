"""drop the is_published column

Revision ID: e2b5c8d1f703
Revises: c9e1f4b7d620
Create Date: 2026-10-30 12:40:00.000000

ADR 0023 makes the coverage a read: a record is public because a channel's scopes carry it and it is
``HUMAN_APPROVED``, not because a boolean says so. Keeping the column would leave a second
definition that the next write would forget to update — the child approved later would be covered by
the view and still say "not published" on any query that read the old column.

**The migration refuses to drop a decision in silence.** An installation whose collection still
carries ``is_published = true`` rows cannot be converted by this migration: there is no channel to
assign them to (the operator adds channels, and a fresh installation has none — ADR 0023 §1), and
inventing one, or a title for the public site, would be the migration deciding what the institution
publishes. The operator lists the ids, records them, clears the flag and republishes through the
Difusão page after the upgrade. The reference collection measured 0 of 4 844 published, so the
refusal is the exceptional path.

The downgrade recreates the column and its index, all false: the downgrade cannot reconstruct a
decision the scopes now carry, and the ledger of the batches says which ones were taken.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "e2b5c8d1f703"
down_revision: str | Sequence[str] | None = "c9e1f4b7d620"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The index ``3d62b30c117b`` created beside the column.
INDEX = "ix_archive_documents_is_published"


def upgrade() -> None:
    """Drops the column and its index, after refusing to erase a decision it still carries."""
    connection = op.get_bind()
    published = int(
        connection.execute(sa.text("SELECT count(*) FROM archive_documents WHERE is_published")).scalar_one()
    )
    if published:
        raise RuntimeError(
            f"{published} description(s) still carry is_published = true. The column is replaced by the "
            "channel scopes (ADR 0023) and this migration cannot invent a channel for them. Before "
            "upgrading: list them with `SELECT description_id FROM archive_documents WHERE is_published`, "
            "keep that list, run `UPDATE archive_documents SET is_published = false`, upgrade, and "
            "publish them through the Difusão page. The migration refuses to drop the decision silently."
        )
    op.drop_index(INDEX, table_name="archive_documents")
    op.drop_column("archive_documents", "is_published")


def downgrade() -> None:
    """Recreates the column and its index, all false; the scopes and the batch ledger say more."""
    op.add_column(
        "archive_documents",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(INDEX, "archive_documents", ["is_published"], unique=False)
