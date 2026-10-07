"""The liveness and readiness answers an orchestrator reads.

They are deliberately not the probes behind ``GET /api/v1/system/health``. That screen answers
*which piece is down* and is allowed to pay for it: it counts three tables, calls Ollama and does a
``HEAD`` on the bucket, each with its own timeout, because a person is waiting and a partial answer
is the useful one. An orchestrator asks a different question — *should this instance receive
traffic?* — every few seconds, so this probe touches the database and nothing else, and answers with
a status code instead of a JSON field.

The distinction matters operationally. A **liveness** failure restarts the process, so it must never
depend on anything (a database restart would restart the API for no reason). A **readiness** failure
only takes the instance out of the load balancer, which is exactly where the database check belongs.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import NullPool

from memoria_curitibana.core.config import settings
from memoria_curitibana.core.logger import logger

#: Bound on the whole readiness check, in seconds. Short on purpose: an orchestrator is waiting, and
#: a probe that hangs is indistinguishable from a process that is not answering.
READY_TIMEOUT_SECONDS = 2

#: Cap on the error text that reaches the log, in the same spirit as the panel's ``DETAIL_LIMIT``.
DETAIL_LIMIT = 300


@lru_cache(maxsize=1)
def _probe_engine() -> Engine:
    """
    A dedicated engine for the probe, with the timeout enforced by libpq and by the server.

    It is not the application engine on purpose. ``connect_timeout`` bounds a host that is
    unreachable — without it libpq waits for the operating system's TCP timeout, which is minutes,
    and the orchestrator would see a probe that never answers. ``statement_timeout`` bounds a server
    that accepted the connection and then stopped replying. ``NullPool`` keeps no idle connection,
    so the probe cannot report healthy because of one it inherited. Widening the shared engine
    instead would change the behaviour of every request and every worker.
    """
    return create_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": READY_TIMEOUT_SECONDS,
            "options": f"-c statement_timeout={READY_TIMEOUT_SECONDS * 1000}",
        },
    )


def database_answers() -> bool:
    """Whether PostgreSQL accepts a connection and answers a trivial query. Never raises."""
    try:
        with _probe_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        # The detail stays in the log: the endpoint is unauthenticated, and a connection error
        # echoes host and port — more than a probe reachable from the internet needs to disclose.
        logger.warning(f"⛔ O banco não respondeu ao probe de readiness: {str(exc)[:DETAIL_LIMIT]}")
        return False
    return True
