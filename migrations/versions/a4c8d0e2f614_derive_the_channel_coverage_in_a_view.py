"""derive the channel coverage in a view

Revision ID: a4c8d0e2f614
Revises: 9f2a7c1e5b30
Create Date: 2026-10-30 11:32:00.000000

The coverage is one definition, ``archive_document_channels``: a description is on a channel when it
is ``HUMAN_APPROVED``, a positive scope covers it and no negative scope does (ADR 0023). It returns
one row per (description, channel) and names the scope that is the origin of the coverage, so the
page can say "pelo ramo do Fundo A" without re-implementing the predicate.

The statement is a **literal of this revision**, not an import: a migration describes the state it
produced, and ``b7e3f9a1c852`` already replaced this view with one that reads the exclusions view.
The test schema is built by ``create_all``, which does not create views, so it executes the current
constant — and ``testing/unit/diffusion/test_view_sql.py`` fails unless some migration carries that
exact definition, so a change to the constant without a migration cannot pass the suite.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic
revision: str = "a4c8d0e2f614"
down_revision: str | Sequence[str] | None = "9f2a7c1e5b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

COVERAGE_VIEW_SQL = """
CREATE OR REPLACE VIEW archive_document_channels AS
WITH ancestry AS (
    SELECT d.description_id,
           d.path,
           unnest(string_to_array(d.path, '.')) AS node_id
      FROM archive_documents d
     WHERE d.review_status = 'HUMAN_APPROVED'
),
excluded AS MATERIALIZED (
    SELECT e.channel_code, a.description_id
      FROM diffusion_channel_exclusions e
      JOIN ancestry a ON a.node_id = e.node_id
     WHERE e.revoked_at IS NULL
       AND (e.include_descendants OR e.node_id = a.description_id)
)
SELECT DISTINCT ON (a.description_id, s.channel_code)
       a.description_id,
       s.channel_code,
       s.scope_id
  FROM ancestry a
  JOIN diffusion_channel_scopes s ON s.node_id = a.node_id
 WHERE s.revoked_at IS NULL
   AND (s.include_descendants OR s.node_id = a.description_id)
   AND NOT EXISTS (
       SELECT 1
         FROM excluded x
        WHERE x.channel_code = s.channel_code
          AND x.description_id = a.description_id
   )
 ORDER BY a.description_id,
          s.channel_code,
          array_position(string_to_array(a.path, '.'), s.node_id) DESC
"""


def upgrade() -> None:
    """Creates the coverage view over the scopes, the documents' path and the approval."""
    op.execute(COVERAGE_VIEW_SQL)


def downgrade() -> None:
    """Drops the view; the scopes and the decision they record stay."""
    op.execute("DROP VIEW IF EXISTS archive_document_channels")
