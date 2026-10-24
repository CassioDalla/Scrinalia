"""the review queue stores a longer catalogue label

The queue's ``llm_decision`` was declared ``String(50)`` when the only labels it carried were a
judge's ``TAG``/``ENTITY`` verdict. The subject and typology classifiers now write the candidate
label they refused, and both catalogues accept names up to 100 characters
(``archive_macro_categories.name`` and ``archive_typologies.name``). A refusal whose best label is
longer than 50 therefore fails the INSERT — and it fails at the batch commit, taking the run's other
decisions with it.

The column is widened to 100, the longest label a catalogue can hold, and not to ``Text``: the value
is a label or a verdict, not free prose, and the bound is the catalogue's own. The downgrade cannot
represent a row longer than 50 and deliberately does not truncate one: a truncated decision is a
different decision.

Revision ID: c4a9e1f7b2d6
Revises: a3f5c9e21b74
Create Date: 2026-10-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a9e1f7b2d6"
down_revision: str | Sequence[str] | None = "a3f5c9e21b74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Widen the decision label to the longest catalogue name it can carry."""
    op.alter_column(
        "archive_ai_review_queue",
        "llm_decision",
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=True,
    )


def downgrade() -> None:
    """
    Narrow the label back to 50; a longer stored row makes this fail.

    The alternative — truncating the value — would rewrite a decision somebody took. A failed
    downgrade is the honest outcome, and PostgreSQL reports which row it could not represent.
    """
    op.alter_column(
        "archive_ai_review_queue",
        "llm_decision",
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
