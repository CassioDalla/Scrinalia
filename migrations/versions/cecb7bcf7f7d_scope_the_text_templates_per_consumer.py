"""scope the text templates per consumer

Revision ID: cecb7bcf7f7d
Revises: c5b784678746
Create Date: 2026-10-04 13:47:49.184533

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cecb7bcf7f7d"
down_revision: str | Sequence[str] | None = "c5b784678746"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "domain_text_templates",
        sa.Column("scope", sa.ARRAY(sa.String(length=20)), server_default="{EMBEDDING,NER}", nullable=False),
    )
    op.create_check_constraint(
        "chk_text_template_scope",
        "domain_text_templates",
        "array_length(scope, 1) >= 1 AND scope <@ ARRAY['EMBEDDING', 'NER', 'TITLE']::varchar[]",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("chk_text_template_scope", "domain_text_templates", type_="check")
    op.drop_column("domain_text_templates", "scope")
