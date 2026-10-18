"""make the legacy identity stamps read as unknown

The identity-keyed slots of ``execution_log`` promise a producer fingerprint and held ``"DONE"``: a
legal ``StampStatus`` that no reader can tell from an attributed unit. Measured on the reference
collection (4,831 documents, 7,921 tags) before this migration:

| slot | ``"DONE"`` |
| --- | ---: |
| ``worker_ner_v2`` | 1,650 |
| ``worker_quality_validator_v1`` | 1,650 |
| ``worker_macro_category_v1`` (tags) | 921 |
| ``worker_typology_classifier_v2`` | 129 |
| ``worker_ner_v1`` (retired key) | 41 |
| ``worker_typology_classifier_v1`` (retired key) | 41 |
| ``worker_embedding_v1`` | 0 — its 4,831 rows carry a bare MD5, below |

This migration gives that value its honest name, ``PRODUCER_UNKNOWN``, and changes nothing else. It
does **not** invent a producer: a unit whose run is recorded and whose producer is unknown is not a
unit produced by anything in particular. The 3,100-odd documents with no key at all are left alone —
what is true about them is that nothing recorded a run — and so is the embedding's bare MD5, which is
a text hash the worker really wrote. Rewriting it would replace a fact that is true (which text was
read) with one that is false (that the row names no text); the read surface calls it "no producer" by
the slot's own pattern instead (``WorkerStampRepository.count_stamp_breakdown``).

The queue is untouched. ``identity_stamp_conditions`` already treats ``"DONE"`` as "not this
producer", so those units are pending and the next run heals them by writing a real fingerprint —
which ``PRODUCER_UNKNOWN`` reads as on purpose. This is attribution and reporting, never the queue.

The retired ``*_v1`` keys are rewritten too: nothing reads them for the queue any more, but a
``"DONE"`` that names no producer should not survive anywhere in the ledger.

Revision ID: a7c1e5b9d3f2
Revises: f647dd7e6ad2
Create Date: 2026-10-18

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7c1e5b9d3f2"
down_revision: str | Sequence[str] | None = "f647dd7e6ad2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The value a legacy row reads from now on. Spelled out instead of imported: a migration is a
#: snapshot of the ledger at its revision, and importing the application's vocabulary would make it
#: stop being one the day that vocabulary moves.
PRODUCER_UNKNOWN = "PRODUCER_UNKNOWN"

#: The statuses an identity slot may hold. ``ERROR`` is deliberately absent: it is a real failure
#: mark and not a producer nobody named, and no identity slot was measured holding one.
LEGACY_STATUS_VALUES = ("DONE", "True")

#: Every slot whose value is a producer fingerprint, current and retired, per model. The retired keys
#: are listed because the ledger should not keep a lie in a slot no worker reads any more.
IDENTITY_SLOTS: dict[str, tuple[str, ...]] = {
    "archive_documents": (
        "worker_ner_v1",
        "worker_ner_v2",
        "worker_typology_classifier_v1",
        "worker_typology_classifier_v2",
        "worker_embedding_v1",
        "worker_quality_validator_v1",
    ),
    "archive_tags": ("worker_macro_category_v1",),
}


def _rewrite(table: str, keys: tuple[str, ...], value: str, *, from_values: tuple[str, ...]) -> None:
    """Rename one value into another on the given slots of one table."""
    literals = ", ".join(f"'{candidate}'" for candidate in from_values)
    for key in keys:
        op.execute(
            f"UPDATE {table} "
            f"SET execution_log = execution_log || jsonb_build_object('{key}', '{value}') "
            f"WHERE execution_log ->> '{key}' IN ({literals})"
        )


def upgrade() -> None:
    """Rename every legacy status in an identity slot to the name that says what it is."""
    for table, keys in IDENTITY_SLOTS.items():
        _rewrite(table, keys, PRODUCER_UNKNOWN, from_values=LEGACY_STATUS_VALUES)


def downgrade() -> None:
    """
    Restore the previous value, which is the one thing a downgrade can mean here.

    A downgrade reinstates the state the migration removed — including the ambiguity — so it writes
    ``"DONE"`` back. A ``True`` that the upgrade could not have produced is mapped to ``"DONE"`` too:
    ``True`` was the thumbnail's mark and no identity slot was measured holding one.
    """
    for table, keys in IDENTITY_SLOTS.items():
        _rewrite(table, keys, "DONE", from_values=(PRODUCER_UNKNOWN,))
