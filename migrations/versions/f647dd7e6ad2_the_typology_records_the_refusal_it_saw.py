"""the typology records the refusal it saw

``archive_documents.typology_id`` is NULL both when the classifier looked at a description and
refused to give it a drawer, and when the run never reached it. The column cannot say which, and the
score that justified the refusal is lost with it — which is the one number a floor decision needs.

The subject axis already answers this: a tag below the floor enters ``archive_ai_review_queue`` with
``SUBJECT_LOW_CONFIDENCE``, carrying the label it guessed and the confidence, so the curator gets a
decision to make instead of a silence. This adds the typology's half of that vocabulary.

It is a new enum value and not a stamp value on purpose: ``identity_stamp_conditions`` computes
pending as "the stamp is not this identity", so a distinct refusal value would either put the
document back in the queue forever or stop a floor change from reaching it at all (issue #110).

Revision ID: f647dd7e6ad2
Revises: 3f9c1a7be204
Create Date: 2026-10-17 11:10:16.721466

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f647dd7e6ad2"
down_revision: str | Sequence[str] | None = "3f9c1a7be204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Adds the typology's refusal to the anomaly vocabulary."""
    # ``ALTER TYPE ... ADD VALUE`` cannot run inside the transaction a migration normally
    # opens, and the value cannot be used in the same transaction that adds it. Committing
    # first is what PostgreSQL requires; ``IF NOT EXISTS`` keeps a replay idempotent.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE anomaly_type_enum ADD VALUE IF NOT EXISTS 'TYPOLOGY_LOW_CONFIDENCE'")


def downgrade() -> None:
    """
    The enum value is deliberately **kept**, the same choice ``SUBJECT_LOW_CONFIDENCE`` made.

    PostgreSQL cannot remove a value from an enum type, and recreating the type would mean
    rewriting every column that uses it — a destructive dance for a label that is inert once no
    code writes it. A leftover value in an enum is harmless; a downgrade that fails on a
    populated table is not.
    """
