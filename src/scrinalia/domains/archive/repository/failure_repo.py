"""The read model behind the failures screen: one line per root cause, across both ledgers.

The grouping key is the ``error_fingerprint`` column, and this module deliberately **does not compute
it**: PostgreSQL does, from the error text, so the read and the write cannot disagree about what a
root cause is. What lives here is the shape of the answer — a UNION of the two ledgers, an aggregate
per fingerprint, and the most recent occurrence as the sample.

The worker filter is applied to the **rows** and not to the groups: with a worker selected, a group
that also broke the API keeps only its worker occurrences, which is what "this worker failed" means.
An API-only group drops out, because it has no worker to match.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models.enums import FailureSource
from scrinalia.domains.archive.schemas.system_schema import FailureGroupDTO

#: ``seen_at`` falls back to ``queued_at`` because the ordering below is what picks the sample: a
#: NULL would sort first under ``DESC`` and the group would report an occurrence that never happened.
FAILURE_GROUPS_SQL = text(
    """
    WITH failures AS (
        SELECT error_fingerprint AS fingerprint,
               'WORKER'::text   AS source,
               worker_name      AS worker_name,
               error            AS message,
               COALESCE(finished_at, queued_at) AS seen_at,
               NULL::text       AS path,
               NULL::text       AS request_id
          FROM archive_worker_runs
         WHERE error_fingerprint IS NOT NULL
           AND COALESCE(finished_at, queued_at) >= :since
        UNION ALL
        SELECT error_fingerprint,
               'API',
               NULL,
               message,
               occurred_at,
               path,
               request_id
          FROM archive_api_errors
         WHERE error_fingerprint IS NOT NULL
           AND occurred_at >= :since
    ),
    visible AS (
        SELECT * FROM failures WHERE (:worker IS NULL OR worker_name = :worker)
    ),
    grouped AS (
        SELECT fingerprint,
               count(*)                    AS occurrences,
               min(seen_at)                AS first_seen,
               max(seen_at)                AS last_seen,
               array_agg(DISTINCT source)  AS sources,
               array_agg(DISTINCT worker_name) FILTER (WHERE worker_name IS NOT NULL) AS worker_names
          FROM visible
         GROUP BY fingerprint
    ),
    latest AS (
        SELECT DISTINCT ON (fingerprint) fingerprint, message
          FROM visible
         ORDER BY fingerprint, seen_at DESC, source
    ),
    -- The API surface is read on its own axis: a group whose *latest* occurrence is a worker run
    -- still has a route and a request id worth showing, and they would be NULL if the sample row
    -- were the only one consulted. ``LEFT JOIN`` because a worker-only group has neither.
    latest_api AS (
        SELECT DISTINCT ON (fingerprint) fingerprint, path, request_id
          FROM visible
         WHERE source = 'API'
         ORDER BY fingerprint, seen_at DESC
    )
    SELECT g.fingerprint,
           l.message    AS sample,
           g.occurrences,
           g.first_seen,
           g.last_seen,
           g.sources,
           g.worker_names,
           a.path       AS last_path,
           a.request_id AS last_request_id,
           count(*) OVER () AS total
      FROM grouped g
      JOIN latest l USING (fingerprint)
      LEFT JOIN latest_api a USING (fingerprint)
     ORDER BY g.last_seen DESC
     LIMIT :limit
    """
)


class FailureRepository:
    """Reads the grouped failures; the caller owns the transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_groups(self, *, since: datetime, worker: str | None, limit: int) -> tuple[list[FailureGroupDTO], int]:
        """The groups that saw activity since ``since``, most recent first."""
        rows = self.db.execute(FAILURE_GROUPS_SQL, {"since": since, "worker": worker, "limit": limit}).mappings().all()

        items = [
            FailureGroupDTO(
                fingerprint=str(row["fingerprint"]),
                sample=str(row["sample"] or ""),
                occurrences=int(row["occurrences"]),
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                sources=[FailureSource(source) for source in row["sources"]],
                worker_names=sorted(str(name) for name in (row["worker_names"] or [])),
                last_path=row["last_path"],
                last_request_id=row["last_request_id"],
            )
            for row in rows
        ]

        # The window function carries the count of groups before LIMIT, so one query answers both
        # "here is the page" and "how many exist" without a second scan of the two ledgers.
        return items, int(rows[0]["total"]) if rows else 0
