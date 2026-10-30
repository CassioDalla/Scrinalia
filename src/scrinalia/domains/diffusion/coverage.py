"""The one definition of channel coverage (ADR 0023).

A description is exposed on a channel when **all three** hold:

1. its ``review_status`` is ``HUMAN_APPROVED``;
2. a positive scope of that channel covers it — the scope's node itself, or an ancestor whose
   ``include_descendants`` is true;
3. no negative scope of that channel covers it.

``archive_document_channels`` is that predicate, and nothing in the code re-implements it: the
curator's page, the public search, the facets, the counts and the export read this view. Two
implementations would drift, and the drift would be silent — a record exposed on a surface its
curator did not choose.

The view returns **one row per (description, channel)**, with the scope that is the origin of the
coverage. A record under "Fundo A" and "Dossiê B" (both published) is one row for the fundo's scope;
that is what lets the page say "pelo ramo do Fundo A" without a second query, and it is the count a
revoke has to show (what would die with that scope, not what the node contains).

**The branch is read from the materialised path, split into its ids.** ``ancestry`` expands each
approved description into itself and its ancestors, and a scope covers it when the scope's node is
one of them. The alternative — join every scope to every description and test
``path LIKE node_path || '.%'`` — was measured on a seeded collection and did not scale: 4 910
descriptions and 10 scopes answered the public predicate in **32 ms**, and 48 050 with 50 scopes took
**1 281 ms**, because the planner compares each description against every scope. The ancestry join is
linear in the coverage (48 050 descriptions / 43 450 covered answered in **178 ms**, and the public
predicate in **323 ms**). The split assumes a description id carries no dot, the same assumption the
dossier makes when it splits ``path`` to resolve its ancestors; the path is built by joining ids with
a dot, so an id with a dot was already ambiguous.

**The view does not read the channel's lifecycle.** ``enabled`` is the operator's pause, not the
curator's decision: a paused channel keeps its coverage, the curator's page marks it paused, and the
public surface is the one that refuses to serve it. Encoding the pause here would make "Publicadas"
hide what the curator published.

The test schema is built from the models by ``create_all``, which does not create views, so
``testing/conftest.py`` executes this same statement. The migration imports it too. That is
deliberate: unlike a table — whose alembic drift is caught by ``alembic check`` — a view has no
autogenerate twin, and a copy in the tests would let the suite pass against a predicate production
does not have.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, MetaData, String, Table

#: The name every reader spells; a client that hard-codes another is a bug the contract catches.
COVERAGE_VIEW = "archive_document_channels"

CREATE_COVERAGE_VIEW_SQL = f"""
CREATE OR REPLACE VIEW {COVERAGE_VIEW} AS
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

DROP_COVERAGE_VIEW_SQL = f"DROP VIEW IF EXISTS {COVERAGE_VIEW}"


#: The view as a Core table, for the queries that select from it. It lives in its own ``MetaData``
#: and not in ``Base.metadata`` on purpose: ``create_all`` would try to build a table, and
#: ``drop_all`` would fail while the view still depended on the documents.
_coverage_metadata = MetaData()

ARCHIVE_DOCUMENT_CHANNELS = Table(
    COVERAGE_VIEW,
    _coverage_metadata,
    Column("description_id", String(50), primary_key=True),
    Column("channel_code", String(50), primary_key=True),
    Column("scope_id", BigInteger, nullable=False),
)
