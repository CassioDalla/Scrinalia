"""Reads and writes the origin table; the caller owns the transaction.

The repository is deliberately small: it owns the lifecycle and the agenda, not the adapter and not
the run ledger. The scheduler's due query lives here with the same ``FOR UPDATE SKIP LOCKED`` shape
the worker schedules use, so a second scheduler skips an origin another one is advancing instead of
enqueueing the same period twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.core.author import Author, assign_author
from scrinalia.domains.ingestion.models import IngestionOrigin


class IngestionOriginRepository:
    """The origin table: its configuration, its lifecycle and its cron."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, code: str) -> IngestionOrigin | None:
        """One origin, or ``None`` when the table has no row for this code."""
        return self.db.get(IngestionOrigin, code)

    def list_all(self) -> list[IngestionOrigin]:
        """Every row, ordered by code, so a caller that does not know the registry still reads them."""
        return list(self.db.scalars(select(IngestionOrigin).order_by(IngestionOrigin.code)))

    def due(self, now: datetime) -> list[IngestionOrigin]:
        """
        The enabled origins whose agenda is due, locked for this transaction.

        ``FOR UPDATE SKIP LOCKED`` is the second guard after the advisory lock: a handover between
        two scheduler transactions cannot enqueue the same period twice.
        """
        return list(
            self.db.scalars(
                select(IngestionOrigin)
                .where(
                    IngestionOrigin.enabled.is_(True),
                    IngestionOrigin.cron.is_not(None),
                    IngestionOrigin.next_run_at.is_not(None),
                    IngestionOrigin.next_run_at <= now,
                )
                .order_by(IngestionOrigin.next_run_at, IngestionOrigin.code)
                .with_for_update(skip_locked=True)
            )
        )

    def _new(self, code: str) -> IngestionOrigin:
        origin = IngestionOrigin(code=code)
        self.db.add(origin)
        return origin

    def upsert_settings(
        self,
        code: str,
        *,
        enabled: bool,
        config: dict[str, Any],
        options: dict[str, Any],
        author: Author | None,
    ) -> IngestionOrigin:
        """
        Creates or updates the lifecycle and the configuration; the agenda is left alone.

        The agenda is a separate write because it has a separate form and a separate validation
        (cron + IANA zone). Saving the URLs of an origin must not silently reset its schedule.
        """
        origin = self.get(code) or self._new(code)
        origin.enabled = enabled
        origin.config = config
        origin.options = options
        assign_author(origin, "updated_by", author)
        self.db.flush()
        return origin

    def set_schedule(
        self,
        code: str,
        *,
        cron: str | None,
        timezone: str | None,
        next_run_at: datetime | None,
        author: Author | None,
    ) -> IngestionOrigin:
        """Creates or replaces the agenda; ``cron=None`` removes it without deleting the origin."""
        origin = self.get(code) or self._new(code)
        origin.cron = cron
        origin.timezone = timezone
        origin.next_run_at = next_run_at
        assign_author(origin, "updated_by", author)
        self.db.flush()
        return origin

    def advance(
        self,
        origin: IngestionOrigin,
        *,
        now: datetime,
        next_run_at: datetime,
        enqueued: bool,
    ) -> None:
        """
        The scheduler's own write: it advances the period and records whether it enqueued or skipped.

        It does not touch ``updated_by``: the agenda's author is the person who saved it, and the
        scheduler must not claim a human authored the tick. The ``last_*`` columns are what let the
        panel say "ran at 02:00" and "skipped at 03:00" without inventing a row.
        """
        if enqueued:
            origin.last_enqueued_at = now
        else:
            origin.last_skipped_at = now
        origin.next_run_at = next_run_at
        self.db.flush()
