"""The live runner registry: who is connected, what it accepts and when it last signalled.

ADR 0014 makes the database the only channel between the API and a runner: the API never calls a
runner, it reads this table. A runner registers when it starts, renews its own row with the same
heartbeat that renews its runs, and marks itself stopped on the way out. The row is kept after the
stop — the panel and the ledger are allowed to remember a runner, and a crash leaves the row behind
so the panel can show it as offline instead of making it disappear.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, and_, case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models.operations import WorkerRunner
from scrinalia.domains.archive.schemas.system_schema import WorkerRunnerDTO


class WorkerRunnerRepository:
    """Reads and writes the runner registry; the caller owns the transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register(
        self,
        runner_id: str,
        *,
        name: str,
        hostname: str,
        version: str | None,
        capabilities: Sequence[str],
        concurrency: int,
        heartbeat_seconds: int,
    ) -> None:
        """
        Registers a runner, or refreshes the row of one restarted with the same identifier.

        The upsert is deliberate: ``--id`` may be stable across restarts, and the panel should show
        one row per runner, not a row per process launch. ``stopped_at`` returns to ``NULL`` because
        the runner is alive again, and ``started_at`` moves to the new start.
        """
        values = {
            "name": name,
            "hostname": hostname,
            "version": version,
            "capabilities": list(capabilities),
            "concurrency": concurrency,
            "heartbeat_seconds": heartbeat_seconds,
            "started_at": func.now(),
            "last_heartbeat_at": func.now(),
            "stopped_at": None,
        }
        self.db.execute(
            insert(WorkerRunner)
            .values(runner_id=runner_id, **values)
            .on_conflict_do_update(index_elements=[WorkerRunner.runner_id], set_=values)
        )
        self.db.flush()

    def heartbeat(self, runner_id: str) -> bool:
        """Renews the runner's own row; ``False`` means it was stopped (or never registered)."""
        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRunner)
                .where(WorkerRunner.runner_id == runner_id, WorkerRunner.stopped_at.is_(None))
                .values(last_heartbeat_at=func.now())
            ),
        )
        self.db.flush()
        return bool(result.rowcount)

    def stop(self, runner_id: str) -> bool:
        """Marks a graceful stop; a crash leaves ``stopped_at`` NULL and the heartbeat decides."""
        result = cast(
            CursorResult[Any],
            self.db.execute(
                update(WorkerRunner)
                .where(WorkerRunner.runner_id == runner_id, WorkerRunner.stopped_at.is_(None))
                .values(stopped_at=func.now())
            ),
        )
        self.db.flush()
        return bool(result.rowcount)

    def list(self) -> list[WorkerRunner]:
        """The registry rows, most recently alive first."""
        return list(self.db.scalars(select(WorkerRunner).order_by(WorkerRunner.last_heartbeat_at.desc())).all())

    def list_for_panel(self) -> list[WorkerRunnerDTO]:
        """
        The registry as the panel reads it, with ``online`` computed by PostgreSQL.

        Online is the heartbeat within three of the runner's **own** declared intervals: a runner
        configured with a slower heartbeat would otherwise be declared dead between two beats. The
        API's clock does not enter the answer, for the same reason the lease does not use it.
        """
        online = case(
            (
                and_(
                    WorkerRunner.stopped_at.is_(None),
                    WorkerRunner.last_heartbeat_at
                    > func.now() - func.make_interval(0, 0, 0, 0, 0, 0, WorkerRunner.heartbeat_seconds * 3),
                ),
                True,
            ),
            else_=False,
        )
        rows = self.db.execute(
            select(WorkerRunner, online.label("online")).order_by(WorkerRunner.last_heartbeat_at.desc())
        ).all()
        return [
            WorkerRunnerDTO(
                runner_id=runner.runner_id,
                name=runner.name,
                hostname=runner.hostname,
                version=runner.version,
                capabilities=list(runner.capabilities),
                concurrency=runner.concurrency,
                started_at=runner.started_at,
                last_heartbeat_at=runner.last_heartbeat_at,
                stopped_at=runner.stopped_at,
                online=bool(is_online),
            )
            for runner, is_online in rows
        ]
