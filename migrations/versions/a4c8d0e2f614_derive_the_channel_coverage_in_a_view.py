"""derive the channel coverage in a view

Revision ID: a4c8d0e2f614
Revises: 9f2a7c1e5b30
Create Date: 2026-10-30 11:32:00.000000

The coverage is one definition, ``archive_document_channels``: a description is on a channel when it
is ``HUMAN_APPROVED``, a positive scope covers it and no negative scope does (ADR 0023). It returns
one row per (description, channel) and names the scope that is the origin of the coverage, so the
page can say "pelo ramo do Fundo A" without re-implementing the predicate.

The statement is imported from ``scrinalia.domains.diffusion.coverage`` and not repeated here: the
test schema is built by ``create_all``, which does not create views, so the tests execute the same
constant — a copy would let the suite pass against a predicate production does not have. Unlike a
table, a view has no ``alembic check`` twin; a later change to the view is a new migration that runs
``CREATE OR REPLACE VIEW`` again.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from scrinalia.domains.diffusion.coverage import CREATE_COVERAGE_VIEW_SQL, DROP_COVERAGE_VIEW_SQL

# revision identifiers, used by Alembic
revision: str = "a4c8d0e2f614"
down_revision: str | Sequence[str] | None = "9f2a7c1e5b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    """Creates the coverage view over the scopes, the documents' path and the approval."""
    op.execute(CREATE_COVERAGE_VIEW_SQL)


def downgrade() -> None:
    """Drops the view; the scopes and the decision they record stay."""
    op.execute(DROP_COVERAGE_VIEW_SQL)
