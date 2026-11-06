"""The one definition of channel coverage (ADR 0023).

A description is exposed on a channel when **all three** hold:

1. its ``review_status`` is ``HUMAN_APPROVED``;
2. a positive scope of that channel covers it — the scope's node itself, or an ancestor whose
   ``include_descendants`` is true;
3. no negative scope of that channel covers it.

Two views, one concept each. ``archive_document_channel_exclusions`` is the negative set — the
descriptions each channel must not expose, with the exclusion that covers them — and
``archive_document_channels`` composes it with the approval and the positive scopes. Splitting them is
what lets the curator's preview say *why* a record is skipped ("excluded" instead of "not covered")
without writing the exclusion predicate a second time.

``archive_document_channels`` returns **one row per (description, channel)**, with the scope that is
the origin of the coverage. A record under "Fundo A" and "Dossiê B" (both published) is one row for
the fundo's scope; that is what lets the page say "pelo ramo do Fundo A" without a second query, and
it is the count a revoke has to show (what would die with that scope, not what the node contains).

**The branch is read from the materialised path, split into its ids.** ``ancestry`` expands each
description into itself and its ancestors, and a scope covers it when the scope's node is one of
them. The alternative — join every scope to every description and test
``path LIKE node_path || '.%'`` — was measured on a seeded collection and did not scale: 4 910
descriptions and 10 scopes answered the public predicate in **32 ms**, and 48 050 with 50 scopes took
**1 281 ms**, because the planner compares each description against every scope. The ancestry join is
linear in the coverage (48 050 descriptions / 43 450 covered answered in **178 ms**, and the public
predicate in **323 ms**). The split assumes a description id carries no dot, the same assumption the
dossier makes when it splits ``path`` to resolve its ancestors; the path is built by joining ids with
a dot, so an id with a dot was already ambiguous.

**The views do not read the channel's lifecycle.** ``enabled`` is the operator's pause, not the
curator's decision: a paused channel keeps its coverage, the curator's page marks it paused, and the
public surface is the one that refuses to serve it. Encoding the pause here would make "Publicadas"
hide what the curator published.

The test schema is built from the models by ``create_all``, which does not create views, so
``testing/conftest.py`` executes these same statements. The migrations keep their own literal — the
state each one produced — and ``testing/unit/diffusion/test_view_sql.py`` pins the pair: the current
constant has to be the one a migration ran, so a change here without a migration is a failing test
instead of a database whose views disagree with the code.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, MetaData, String, Table

#: The name every reader spells; a client that hard-codes another is a bug the contract catches.
COVERAGE_VIEW = "archive_document_channels"

#: The negative set, read by the coverage view and by the preview that has to say "excluded".
EXCLUSIONS_VIEW = "archive_document_channel_exclusions"

CREATE_EXCLUSIONS_VIEW_SQL = f"""
CREATE OR REPLACE VIEW {EXCLUSIONS_VIEW} AS
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

CREATE_COVERAGE_VIEW_SQL = f"""
CREATE OR REPLACE VIEW {COVERAGE_VIEW} AS
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
         FROM {EXCLUSIONS_VIEW} x
        WHERE x.channel_code = s.channel_code
          AND x.description_id = a.description_id
   )
 ORDER BY a.description_id,
          s.channel_code,
          array_position(string_to_array(a.path, '.'), s.node_id) DESC
"""

DROP_EXCLUSIONS_VIEW_SQL = f"DROP VIEW IF EXISTS {EXCLUSIONS_VIEW}"

DROP_COVERAGE_VIEW_SQL = f"DROP VIEW IF EXISTS {COVERAGE_VIEW}"


#: The views as Core tables, for the queries that select from them. They live in their own
#: ``MetaData`` and not in ``Base.metadata`` on purpose: ``create_all`` would try to build a table,
#: and ``drop_all`` would fail while the views still depended on the documents.
_view_metadata = MetaData()

ARCHIVE_DOCUMENT_CHANNELS = Table(
    COVERAGE_VIEW,
    _view_metadata,
    Column("description_id", String(50), primary_key=True),
    Column("channel_code", String(50), primary_key=True),
    Column("scope_id", BigInteger, nullable=False),
)

ARCHIVE_DOCUMENT_CHANNEL_EXCLUSIONS = Table(
    EXCLUSIONS_VIEW,
    _view_metadata,
    Column("description_id", String(50), primary_key=True),
    Column("channel_code", String(50), primary_key=True),
    Column("scope_id", BigInteger, nullable=False),
)
