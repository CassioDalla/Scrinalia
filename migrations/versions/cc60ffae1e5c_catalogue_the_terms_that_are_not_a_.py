"""catalogue the terms that are not a subject

Revision ID: cc60ffae1e5c
Revises: 8bbb7bd76c13
Create Date: 2026-10-04 20:39:01.220467

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cc60ffae1e5c"
down_revision: str | Sequence[str] | None = "8bbb7bd76c13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Creates the curated catalogue of non-subjects, and the queue reason that feeds it.

    Why this exists next to the deterministic guard: the guard matches a **form** and caught
    one of the four non-subjects in the labelled set. ``pessoas`` (166 documents), ``vista
    aérea`` (89) and ``capanema`` (91) have no shape a rule can match — they are judgements,
    and the model cannot abstain, so it answers confidently and wrongly. This table is where
    a human records the decision instead.

    The table starts empty on purpose. The guard needs no curation (it is code, pinned by
    tests); a curated exclusion is a decision, and seeding one would be inventing a verdict
    nobody made.
    """
    op.create_table(
        "domain_subject_exclusions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("term", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="HUMAN", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('HUMAN', 'RULE')", name="chk_subject_exclusion_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_domain_subject_exclusions_term"),
        "domain_subject_exclusions",
        ["term"],
        unique=True,
    )

    # ``ALTER TYPE ... ADD VALUE`` cannot run inside the transaction a migration normally
    # opens, and the value cannot be used in the same transaction that adds it. Committing
    # first is what PostgreSQL requires; ``IF NOT EXISTS`` keeps a replay idempotent.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE anomaly_type_enum ADD VALUE IF NOT EXISTS 'SUBJECT_LOW_CONFIDENCE'")


def downgrade() -> None:
    """
    Drops the catalogue. The enum value is deliberately **kept**.

    PostgreSQL cannot remove a value from an enum type, and recreating the type would mean
    rewriting every column that uses it — a destructive dance for a label that is inert once
    no code writes it. A leftover value in an enum is harmless; a downgrade that fails on a
    populated table is not.
    """
    op.drop_index(op.f("ix_domain_subject_exclusions_term"), table_name="domain_subject_exclusions")
    op.drop_table("domain_subject_exclusions")
