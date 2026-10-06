"""Persisted default configuration of the AI workers, with its audit trail.

The row is partial on purpose: a field left ``None`` means "keep following the code". The runner
reads it as the middle rung of the precedence (explicit argument > this row > the signature
default), and the panel shows which fields are overridden so an operator can tell a deliberate
choice from a default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.models.operations import WorkerSetting, WorkerSettingRevision


def snapshot(setting: WorkerSetting | None) -> dict[str, Any] | None:
    """The comparable form of a settings row, used by the revision's before/after."""
    if setting is None:
        return None
    return {
        "engine_name": setting.engine_name,
        "preset": setting.preset,
        "db_batch_size": setting.db_batch_size,
        "options": dict(setting.options or {}),
    }


class WorkerSettingsRepository:
    """Reads and writes the worker defaults; the caller owns the transaction."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, worker_name: str) -> WorkerSetting | None:
        return self.db.get(WorkerSetting, worker_name)

    def get_all(self) -> dict[str, WorkerSetting]:
        """Every override, keyed by worker, in one query for the panel."""
        return {setting.worker_name: setting for setting in self.db.scalars(select(WorkerSetting)).all()}

    def upsert(
        self,
        worker_name: str,
        *,
        engine_name: str | None,
        preset: str | None,
        db_batch_size: int | None,
        options: dict[str, Any],
        changed_by: str | None,
    ) -> WorkerSetting:
        """
        Writes the override and its revision.

        The revision is written in the same transaction as the row: a settings change with no
        audit entry would be indistinguishable from a default.
        """
        setting = self.db.get(WorkerSetting, worker_name)
        before = snapshot(setting)

        if setting is None:
            setting = WorkerSetting(worker_name=worker_name)
            self.db.add(setting)

        setting.engine_name = engine_name
        setting.preset = preset
        setting.db_batch_size = db_batch_size
        setting.options = options or {}
        setting.updated_by = changed_by
        setting.updated_at = datetime.now(UTC)
        self.db.flush()

        self.db.add(
            WorkerSettingRevision(
                worker_name=worker_name,
                before=before,
                after=snapshot(setting),
                changed_by=changed_by,
            )
        )
        self.db.flush()
        return setting

    def clear(self, worker_name: str, *, changed_by: str | None) -> bool:
        """Removes the override so the worker follows the code again. Returns whether it existed."""
        setting = self.db.get(WorkerSetting, worker_name)
        if setting is None:
            return False

        before = snapshot(setting)
        self.db.delete(setting)
        self.db.add(WorkerSettingRevision(worker_name=worker_name, before=before, after=None, changed_by=changed_by))
        self.db.flush()
        return True

    def list_revisions(self, worker_name: str, *, limit: int, offset: int) -> tuple[list[WorkerSettingRevision], int]:
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(WorkerSettingRevision)
                .where(WorkerSettingRevision.worker_name == worker_name)
            )
            or 0
        )
        rows = self.db.scalars(
            select(WorkerSettingRevision)
            .where(WorkerSettingRevision.worker_name == worker_name)
            .order_by(WorkerSettingRevision.changed_at.desc(), WorkerSettingRevision.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total
