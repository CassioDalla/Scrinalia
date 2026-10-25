"""The schema-head check the runner and the scheduler share before they touch the queue.

Two machines, one release (ADR 0014): the API owns the migrations, and a process that claims the
queue against a schema it does not understand would fail every run with a column error. The check
is cheap, runs before the first claim or tick, and is skipped with a warning when the code's head is
unreadable (a wheel without ``migrations/``), because then there is nothing to compare against.

It lives here and not in either daemon so the runner and the scheduler cannot drift into two
different versions of "is the schema at the head?" (ADR 0015).
"""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from scrinalia.core.database import SessionFactory, create_runner_session
from scrinalia.core.logger import logger


def schema_head() -> str | None:
    """The head of the code's Alembic history, or ``None`` when the checkout has no migrations."""
    try:
        return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    except Exception as exc:
        logger.warning(f"⚠️ Could not read the Alembic head: {exc}")
        return None


def current_schema_revision(session_factory: SessionFactory = create_runner_session) -> str | None:
    """The revision the database records, or ``None`` when the table/row is missing."""
    try:
        with session_factory() as db:
            return db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except Exception as exc:
        logger.warning(f"⚠️ Could not read the schema revision: {exc}")
        return None


def assert_schema_at_head(session_factory: SessionFactory = create_runner_session) -> None:
    """
    Refuses to run against a schema behind the code.

    The scheduler and the runner call it with their own session factory: the runner's may be the
    least-privilege credential, the scheduler's is the API's. The comparison is the same.
    """
    head = schema_head()
    if head is None:
        logger.warning("⚠️ The Alembic head is unavailable; the schema revision cannot be checked.")
        return
    current = current_schema_revision(session_factory)
    if current != head:
        raise SystemExit(
            f"The database is at {current or 'no alembic_version'}, the code is at {head}. "
            "Apply the API's migrations before starting the runner or the scheduler (ADR 0014)."
        )
