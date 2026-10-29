"""drop the seeded origin that was never used

Revision ID: f1090f825a94
Revises: 6c46426b048a
Create Date: 2026-10-26 20:20:36.230927

The ``pmc`` row is seeded by ``44a1b2c3d4e5`` on every install, so the origins screen could never
show its empty state (#206). This revision deletes it only when it is still the seed: nobody edited
it (``updated_by`` is null), it has no agenda, and no raw/staging/archive/queue/run row names it. An
upgrade that already read the reference site, or whose operator touched the origin, keeps the row
and its configuration.

The manual and CSV rows are **not** touched: the manual form and the CSV import refuse to work
without them, and their rows are the entry paths' provenance. They are not sources, and the screen
shows them read-only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1090f825a94"
down_revision: str | Sequence[str] | None = "6c46426b048a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Deletes the seeded ``pmc`` row when it has no history, no agenda and no author."""
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM ingestion_origins
            WHERE code = 'pmc'
              AND updated_by IS NULL
              AND cron IS NULL
              AND NOT EXISTS (SELECT 1 FROM raw_data          WHERE origin_code = 'pmc')
              AND NOT EXISTS (SELECT 1 FROM scraping_queue    WHERE origin_code = 'pmc')
              AND NOT EXISTS (SELECT 1 FROM staging_documents WHERE origin_code = 'pmc')
              AND NOT EXISTS (SELECT 1 FROM archive_documents WHERE origin_code = 'pmc')
              AND NOT EXISTS (SELECT 1 FROM archive_worker_runs WHERE origin_code = 'pmc')
            """
        )
    )


def downgrade() -> None:
    """No-op: the seed's configuration came from the environment, and the deletion is not reversible.

    Re-inserting the row would invent a configuration the operator did not choose. The adapter's
    ``PUBLIC_SCRAPE_*`` fallback is what keeps the reference origin working after the row is gone.
    """
