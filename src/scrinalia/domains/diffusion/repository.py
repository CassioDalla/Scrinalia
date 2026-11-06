"""Reads and writes the channel table; the caller owns the transaction.

It mirrors ``domains/ingestion/origin_repo.py``: the repository owns the lifecycle and the agenda,
not the registry and not the run ledger. The scheduler's due query lives here because the agenda is
the row's, and the advance is written by the scheduler on the same locked row (#212).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.core.author import Author, assign_author
from scrinalia.domains.diffusion.models import DiffusionChannel


class DiffusionChannelRepository:
    """The channel table: its configuration, its lifecycle and its cron."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, code: str) -> DiffusionChannel | None:
        """One channel, or ``None`` when the table has no row for this code."""
        return self.db.get(DiffusionChannel, code)

    def list_all(self) -> list[DiffusionChannel]:
        """Every row, ordered by code, so a caller that does not know the registry still reads them."""
        return list(self.db.scalars(select(DiffusionChannel).order_by(DiffusionChannel.code)))

    def due(self, now: datetime) -> list[DiffusionChannel]:
        """
        The enabled channels whose agenda is due, locked for this transaction.

        ``FOR UPDATE SKIP LOCKED`` is the second guard after the scheduler's advisory lock: a
        handover between two scheduler transactions cannot enqueue the same period twice. A paused
        channel is not due, and a channel without a cron or a ``next_run_at`` has no agenda to fire.
        """
        return list(
            self.db.scalars(
                select(DiffusionChannel)
                .where(
                    DiffusionChannel.enabled.is_(True),
                    DiffusionChannel.cron.is_not(None),
                    DiffusionChannel.next_run_at.is_not(None),
                    DiffusionChannel.next_run_at <= now,
                )
                .order_by(DiffusionChannel.next_run_at, DiffusionChannel.code)
                .with_for_update(skip_locked=True)
            )
        )

    def _new(self, code: str) -> DiffusionChannel:
        channel = DiffusionChannel(code=code)
        self.db.add(channel)
        return channel

    def upsert_settings(
        self,
        code: str,
        *,
        enabled: bool | None = None,
        config: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        author: Author | None = None,
    ) -> DiffusionChannel:
        """
        Creates or updates the lifecycle and the configuration; the agenda is left alone.

        An omitted field is left as it was: the agenda is a separate write because it has its own
        form and its own validation (cron + IANA zone), and pausing a channel must not reset the
        configuration the operator already saved.
        """
        channel = self.get(code) or self._new(code)
        if enabled is not None:
            channel.enabled = enabled
        if config is not None:
            channel.config = config
        if options is not None:
            channel.options = options
        assign_author(channel, "updated_by", author)
        self.db.flush()
        return channel

    def set_schedule(
        self,
        code: str,
        *,
        cron: str | None,
        timezone: str | None,
        next_run_at: datetime | None,
        author: Author | None = None,
    ) -> DiffusionChannel:
        """Creates or replaces the agenda; ``cron=None`` removes it without deleting the channel."""
        channel = self.get(code) or self._new(code)
        channel.cron = cron
        channel.timezone = timezone
        channel.next_run_at = next_run_at
        assign_author(channel, "updated_by", author)
        self.db.flush()
        return channel
