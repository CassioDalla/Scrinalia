"""add the tag facet table

Revision ID: 16b3b222c85c
Revises: 63bcc576d926
Create Date: 2026-10-04 19:41:33.866460

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16b3b222c85c"
down_revision: str | Sequence[str] | None = "63bcc576d926"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Creates the non-subject axis of a tag.

    ``archive_tags.macro_category_id`` holds a subject and only a subject. Tags such as
    ``ippuc`` (2.376 documents) and ``curitiba`` (1.865) have no subject but a clear
    institution/place axis, and forcing them into the subject drawers is one of the two
    measured causes of the systematic misclassification this phase fixes. Nothing is
    backfilled here: populating a facet is a curation act, so the table starts empty.
    """
    op.create_table(
        "archive_tag_facets",
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("facet_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("facet_type IN ('INSTITUTION', 'PLACE')", name="chk_tag_facet_type"),
        sa.ForeignKeyConstraint(["tag_id"], ["archive_tags.tag_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tag_id", "facet_type"),
    )
    op.create_index(
        "ix_archive_tag_facets_type_value",
        "archive_tag_facets",
        ["facet_type", "value"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_archive_tag_facets_type_value", table_name="archive_tag_facets")
    op.drop_table("archive_tag_facets")
