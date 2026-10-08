"""let the curator write the classifier label

Revision ID: 8bbb7bd76c13
Revises: f8760cab6d12
Create Date: 2026-10-04 19:50:58.167769

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8bbb7bd76c13"
down_revision: str | Sequence[str] | None = "f8760cab6d12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Gives every drawer the proposition the NLI model reads.

    ``mDeBERTa-mnli`` answers "does the text entail the label?", so the label has to be a
    sentence. A noun phrase is not one, and the entailment ends up choosing by lexical
    proximity: measured on the real collection, ``alvenaria`` and ``1924`` were both
    classified into "Mobilidade e Transporte" with 0.42 and 0.73 confidence. Writing the
    hypothesis is a curation decision — the archivist knows what the drawer means — so it
    lives in a column and is edited without a deploy.

    Nullable on purpose: ``NULL`` falls back to the drawer name, which is the behaviour the
    repository had before this column existed, so the migration changes nothing until a
    curator writes a label.
    """
    op.add_column("archive_macro_categories", sa.Column("classifier_label", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("archive_macro_categories", "classifier_label")
