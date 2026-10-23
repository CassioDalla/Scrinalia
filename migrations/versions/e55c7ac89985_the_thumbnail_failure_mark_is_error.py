"""the thumbnail failure mark is error

Issue #149: ``StampStatus`` carried ``"True"`` only because the thumbnail worker wrote it into
``thumbnail_failed`` — a boolean serialised into a status vocabulary. The value is never read: the
thumbnail queue and its ``count_failed`` both key on the **presence** of ``thumbnail_failed``, so
this migration changes what the ledger says and not what the queue does.

Measured on the reference collection (``memoriacuritibana``) before the migration: **0** rows carry
``thumbnail_failed``; the rewrite was exercised on a scratch database with one row, and the
downgrade returned it to ``"True"``.

Revision ID: e55c7ac89985
Revises: a7c1e5b9d3f2
Create Date: 2026-10-22

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e55c7ac89985"
down_revision: str | Sequence[str] | None = "a7c1e5b9d3f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The key whose value changes. It is the thumbnail worker's failure ledger; the queue reads the
#: presence of the key, not the value.
THUMBNAIL_FAILED_KEY = "thumbnail_failed"

#: The value before and after. Spelled out instead of imported: a migration is a snapshot of the
#: ledger at its revision, and importing the application's vocabulary would make it stop being one
#: the day that vocabulary moves.
LEGACY_FAILURE = "True"
FAILURE = "ERROR"


def _rewrite(*, from_value: str, to_value: str) -> None:
    """Rename the thumbnail's failure value where it is the legacy spelling."""
    op.execute(
        f"UPDATE archive_documents "
        f"SET execution_log = execution_log || jsonb_build_object('{THUMBNAIL_FAILED_KEY}', '{to_value}') "
        f"WHERE execution_log ->> '{THUMBNAIL_FAILED_KEY}' = '{from_value}'"
    )


def upgrade() -> None:
    """Rename the boolean failure mark to the ``ERROR`` every other ledger uses."""
    _rewrite(from_value=LEGACY_FAILURE, to_value=FAILURE)


def downgrade() -> None:
    """Restore the previous value, which is the one thing a downgrade can mean here."""
    _rewrite(from_value=FAILURE, to_value=LEGACY_FAILURE)
