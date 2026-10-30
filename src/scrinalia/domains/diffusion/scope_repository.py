"""Writes the publication scopes and the batch ledger; the caller owns the transaction.

The rows are never deleted: revoking writes ``revoked_at`` and reactivating clears it, so the scope
table keeps the history of the decision and the partial unique index keeps a single active row per
node and channel. The batch ledger records the gesture on top of that — one row per scope touched,
with the state before and after and a snapshot of the node — which is what the undo reads.

Nothing here computes coverage: that is the view (``coverage.py``), and these are the writes its
predicate is derived from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scrinalia.core.author import Author, assign_author, author_columns
from scrinalia.domains.diffusion.models import (
    DiffusionChannelExclusion,
    DiffusionChannelScope,
    DiffusionPublicationBatch,
    DiffusionPublicationEntry,
)
from scrinalia.domains.diffusion.publication_schemas import PublicationAction


class DiffusionScopeRepository:
    """The active scopes of a channel, and the writes that create, revoke and restore them."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads -----------------------------------------------------------------------------------

    def active_inclusion(self, channel_code: str, node_id: str) -> DiffusionChannelScope | None:
        """The positive scope of that node and channel, or ``None`` when it is not published there."""
        return self.db.scalars(
            select(DiffusionChannelScope).where(
                DiffusionChannelScope.channel_code == channel_code,
                DiffusionChannelScope.node_id == node_id,
                DiffusionChannelScope.revoked_at.is_(None),
            )
        ).first()

    def active_exclusion(self, channel_code: str, node_id: str) -> DiffusionChannelExclusion | None:
        """The negative scope of that node and channel, or ``None``."""
        return self.db.scalars(
            select(DiffusionChannelExclusion).where(
                DiffusionChannelExclusion.channel_code == channel_code,
                DiffusionChannelExclusion.node_id == node_id,
                DiffusionChannelExclusion.revoked_at.is_(None),
            )
        ).first()

    def active_inclusions_for(self, channel_code: str, node_ids: list[str]) -> dict[str, DiffusionChannelScope]:
        """The active positive scopes of a set of nodes, one query for a whole selection."""
        if not node_ids:
            return {}
        rows = self.db.scalars(
            select(DiffusionChannelScope).where(
                DiffusionChannelScope.channel_code == channel_code,
                DiffusionChannelScope.node_id.in_(node_ids),
                DiffusionChannelScope.revoked_at.is_(None),
            )
        ).all()
        return {row.node_id: row for row in rows}

    # --- writes ----------------------------------------------------------------------------------

    def create_inclusion(
        self,
        channel_code: str,
        node_id: str,
        *,
        include_descendants: bool,
        note: str | None,
        author: Author | None,
    ) -> DiffusionChannelScope:
        """Adds the positive scope; the unique index refuses a second active one on the same node."""
        scope = DiffusionChannelScope(
            channel_code=channel_code,
            node_id=node_id,
            include_descendants=include_descendants,
            note=note,
            **author_columns("created_by", author),
        )
        self.db.add(scope)
        self.db.flush()
        return scope

    def create_exclusion(
        self,
        channel_code: str,
        node_id: str,
        *,
        include_descendants: bool,
        reason: str | None,
        author: Author | None,
    ) -> DiffusionChannelExclusion:
        """Adds the negative scope, with the reason the curator gave."""
        exclusion = DiffusionChannelExclusion(
            channel_code=channel_code,
            node_id=node_id,
            include_descendants=include_descendants,
            reason=reason,
            **author_columns("created_by", author),
        )
        self.db.add(exclusion)
        self.db.flush()
        return exclusion

    def revoke_inclusion(self, scope: DiffusionChannelScope, author: Author | None) -> None:
        """Revokes the positive scope; the row stays, with who revoked it and when."""
        scope.revoked_at = datetime.now(UTC)
        assign_author(scope, "revoked_by", author)

    def revoke_exclusion(self, exclusion: DiffusionChannelExclusion, author: Author | None) -> None:
        """Revokes the negative scope; the record may become visible again if a scope covers it."""
        exclusion.revoked_at = datetime.now(UTC)
        assign_author(exclusion, "revoked_by", author)

    def restore_inclusion(self, scope: DiffusionChannelScope) -> None:
        """Reactivates a revoked positive scope — the undo of a revoke."""
        scope.revoked_at = None
        scope.revoked_by = None
        scope.revoked_by_user_id = None

    def restore_exclusion(self, exclusion: DiffusionChannelExclusion) -> None:
        """Reactivates a revoked negative scope — the undo of an unexclude."""
        exclusion.revoked_at = None
        exclusion.revoked_by = None
        exclusion.revoked_by_user_id = None


class PublicationBatchRepository:
    """The batch and its entries: one gesture, its scope rows and the state each one was in."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        action: PublicationAction,
        selection: dict[str, Any],
        note: str | None,
        author: Author | None,
    ) -> DiffusionPublicationBatch:
        """Opens the batch; the counts are filled by the caller as the entries are written."""
        batch = DiffusionPublicationBatch(
            action=action.value,
            selection=selection,
            note=note,
            **author_columns("requested_by", author),
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def add_entry(
        self,
        batch: DiffusionPublicationBatch,
        *,
        channel_code: str,
        kind: str,
        scope_id: int | None,
        node_id: str,
        node_path: str,
        node_title: str | None,
        include_descendants: bool,
        was_active: bool,
        is_active: bool,
    ) -> DiffusionPublicationEntry:
        """Records one scope row the gesture created, revoked or restored."""
        entry = DiffusionPublicationEntry(
            batch_id=batch.batch_id,
            channel_code=channel_code,
            kind=kind,
            scope_id=scope_id,
            node_id=node_id,
            node_path=node_path,
            node_title=node_title,
            include_descendants=include_descendants,
            was_active=was_active,
            is_active=is_active,
        )
        self.db.add(entry)
        return entry

    def get(self, batch_id: int) -> DiffusionPublicationBatch | None:
        return self.db.get(DiffusionPublicationBatch, batch_id)

    def entries(self, batch_id: int) -> list[DiffusionPublicationEntry]:
        """The batch's entries, in the order they were written."""
        return list(
            self.db.scalars(
                select(DiffusionPublicationEntry)
                .where(DiffusionPublicationEntry.batch_id == batch_id)
                .order_by(DiffusionPublicationEntry.entry_id)
            ).all()
        )

    def channels_of(self, batch_id: int) -> list[str]:
        """The channels the batch touched, from its entries, ordered by code."""
        return list(
            self.db.scalars(
                select(DiffusionPublicationEntry.channel_code)
                .where(DiffusionPublicationEntry.batch_id == batch_id)
                .distinct()
                .order_by(DiffusionPublicationEntry.channel_code)
            ).all()
        )

    def list(self, limit: int, offset: int) -> tuple[list[DiffusionPublicationBatch], int]:
        """The history, newest first, with its total."""
        total = int(self.db.scalar(select(func.count()).select_from(DiffusionPublicationBatch)) or 0)
        rows = list(
            self.db.scalars(
                select(DiffusionPublicationBatch)
                .order_by(DiffusionPublicationBatch.created_at.desc(), DiffusionPublicationBatch.batch_id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return rows, total

    def mark_undone(self, batch: DiffusionPublicationBatch, author: Author | None) -> None:
        """Closes the batch as undone; a second undo is refused by the service."""
        batch.undone_at = datetime.now(UTC)
        assign_author(batch, "undone_by", author)
