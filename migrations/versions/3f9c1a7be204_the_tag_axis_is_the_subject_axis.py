"""the tag axis is the subject axis

Drops the non-subject axis of a tag (``archive_tag_facets``), gives a banned spelling a provenance
(``domain_stopwords.source``) and makes the subject exclusion's ban exact
(``domain_subject_exclusions.ban_created``). See ADR 0013 and issues #83/#84.

Revision ID: 3f9c1a7be204
Revises: 1ed87326f6f2
Create Date: 2026-10-13 23:40:12.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f9c1a7be204"
down_revision: str | Sequence[str] | None = "1ed87326f6f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Upgrade schema."""
    # The table was read and recorded in ADR 0013 before the drop: one row in the legacy collection
    # (``tag_id=4144``, ``INSTITUTION``, value ``ippuc``). Nothing in the code consumed it — the
    # ``value`` column was written by ``upsert_tag_facet`` and never selected — so the table is one
    # of the two halves of the defect the ADR removes, and a dormant copy would keep the confusion.
    op.drop_index(op.f("ix_archive_tag_facets_type_value"), table_name="archive_tag_facets")
    op.drop_table("archive_tag_facets")

    # The provenance of a ban, so the purge preview can tell a term banned with the archive in mind
    # from one typed by hand. The column arrives on a table that already has rows: the server default
    # fills them, and the backfill then promotes the ones the conflict ledger recorded planting.
    op.add_column(
        "domain_stopwords",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="HUMAN"),
    )
    op.execute(
        """
        UPDATE domain_stopwords AS stopword
           SET source = 'CONFLICT'
          FROM archive_conflict_resolution_log AS resolution
         WHERE resolution.ban_created IS TRUE
           AND resolution.ban_term IS NOT NULL
           AND lower(btrim(resolution.ban_term)) = stopword.word
        """
    )
    op.create_check_constraint(
        "chk_stopword_source", "domain_stopwords", "source IN ('HUMAN', 'CONFLICT', 'EXCLUSION')"
    )

    # The exclusion plants a ban too, and two writers on one unique ``word`` need to know which one
    # did it: ``DELETE /tags/subject-exclusions`` lifts only the ban the exclusion itself created,
    # exactly like ``undo_conflict_resolution`` reads the conflict ledger's own ``ban_created``.
    op.add_column(
        "domain_subject_exclusions",
        sa.Column("ban_created", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("domain_subject_exclusions", "ban_created")
    op.drop_constraint("chk_stopword_source", "domain_stopwords", type_="check")
    op.drop_column("domain_stopwords", "source")

    # Rebuilt with the shape the model carried before ADR 0013. The row the migration recorded is not
    # restored: it was an installation's experiment, and its content lives in the ADR.
    op.create_table(
        "archive_tag_facets",
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("facet_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint("facet_type IN ('INSTITUTION', 'PLACE')", name="chk_tag_facet_type"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tag_id"], ["archive_tags.tag_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tag_id", "facet_type"),
    )
    op.create_index(
        op.f("ix_archive_tag_facets_type_value"), "archive_tag_facets", ["facet_type", "value"], unique=False
    )
