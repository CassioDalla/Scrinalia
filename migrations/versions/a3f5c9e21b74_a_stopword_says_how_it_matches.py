"""a stopword says how it matches

Issue #160: a banned spelling had exactly one rule — it blocked the name and every name containing
it as a whole word — and that rule was right for the merged span it was written for (``iptu`` has to
reject ``IPTU do Exemplo``) and wrong for the generic words that also start proper names (``alameda``
rejected ``Alameda Cabral``, ``caixa`` rejected ``Caixa Econômica``). Measured on the reference
collection, the token rule rejected 115 entity names over 1.288 links and 1.170 documents.

The column defaults to ``TOKEN``, which is the behaviour every existing row had, so this migration
changes no extraction. Which rows become ``EXACT`` is a curation decision taken on the data, not here:
a migration that guessed would move the names by itself, which is what the column exists to let a
person decide.

Revision ID: a3f5c9e21b74
Revises: b4e2c8d17a63
Create Date: 2026-10-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f5c9e21b74"
down_revision: str | Sequence[str] | None = "b4e2c8d17a63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Alembic reads these four from the module namespace (``alembic/script/base.py``): they are the
#: module's public API, and ``__all__`` is what keeps a static reader from taking them for dead code.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

#: The values of ``StopwordMatch``. Spelled out instead of imported: a migration is a snapshot of the
#: schema at its revision, and importing the application's vocabulary would make it stop being one
#: the day that vocabulary moves.
MATCH_MODES = ("TOKEN", "EXACT")


def upgrade() -> None:
    """Add the match mode, defaulting to the token rule every existing row already had."""
    op.add_column(
        "domain_stopwords",
        sa.Column("match_mode", sa.String(length=8), nullable=False, server_default="TOKEN"),
    )
    op.create_check_constraint(
        "chk_stopword_match_mode",
        "domain_stopwords",
        "match_mode IN ('TOKEN', 'EXACT')",
    )


def downgrade() -> None:
    """Drop the column and the rule; the bans themselves stay."""
    op.drop_constraint("chk_stopword_match_mode", "domain_stopwords", type_="check")
    op.drop_column("domain_stopwords", "match_mode")
