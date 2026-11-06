"""let the coverage compose the exclusions view

Revision ID: c9e1f4b7d620
Revises: b7e3f9a1c852
Create Date: 2026-10-30 12:02:00.000000

The exemption that has to say *why* a record is skipped — "excluded", not "not covered" — is the
negative scope itself, so it becomes a view of its own: ``archive_document_channel_exclusions``
returns (description, channel, scope) for the descriptions an exclusion covers, with the nearest
exclusion as the origin. ``archive_document_channels`` composes it with the approval and the positive
scopes instead of repeating the exclusion predicate inside its own WHERE.

One concept, one statement: the coverage no longer knows how an exclusion is resolved, and the
curator's preview reads the negative set without a second implementation. Both literals are the ones
``testing/unit/diffusion/test_view_sql.py`` pins to ``coverage.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic
revision: str = "c9e1f4b7d620"
down_revision: str | Sequence[str] | None = "b7e3f9a1c852"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

EXCLUSIONS_VIEW_SQL = """
CREATE OR REPLACE VIEW archive_document_channel_exclusions AS
SELECT DISTINCT ON (a.description_id, e.channel_code)
       a.description_id,
       e.channel_code,
       e.scope_id
  FROM (
        SELECT d.description_id,
               d.path,
               unnest(string_to_array(d.path, '.')) AS node_id
          FROM archive_documents d
       ) a
  JOIN diffusion_channel_exclusions e
    ON e.node_id = a.node_id
   AND e.revoked_at IS NULL
   AND (e.include_descendants OR e.node_id = a.description_id)
 ORDER BY a.description_id,
          e.channel_code,
          array_position(string_to_array(a.path, '.'), e.node_id) DESC
"""

COVERAGE_VIEW_SQL = """
CREATE OR REPLACE VIEW archive_document_channels AS
WITH ancestry AS (
    SELECT d.description_id,
           d.path,
           unnest(string_to_array(d.path, '.')) AS node_id
      FROM archive_documents d
     WHERE d.review_status = 'HUMAN_APPROVED'
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
         FROM archive_document_channel_exclusions x
        WHERE x.channel_code = s.channel_code
          AND x.description_id = a.description_id
   )
 ORDER BY a.description_id,
          s.channel_code,
          array_position(string_to_array(a.path, '.'), s.node_id) DESC
"""

#: The definition this revision replaced. The downgrade restores it instead of dropping the view:
#: the previous revision's schema is a state another migration described, not an absence.
PREVIOUS_COVERAGE_VIEW_SQL = """
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
    """Creates the exclusions view, then the coverage view that reads it."""
    op.execute(EXCLUSIONS_VIEW_SQL)
    op.execute(COVERAGE_VIEW_SQL)


def downgrade() -> None:
    """Restores the coverage view that carried its own exclusion clause, and drops the new one."""
    op.execute(PREVIOUS_COVERAGE_VIEW_SQL)
    op.execute("DROP VIEW IF EXISTS archive_document_channel_exclusions")
