"""Builders shared by the publication tests: a channel, a node with its path, a scope, an exclusion.

The arrangement is built by hand because ``path`` is materialised and the coverage view reads it; a
test that used the real move service would be testing the move, not the predicate. The helpers keep
the tests about the decision — a branch, a child approved later, the exclusion — and not about the
columns it takes to say so.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.diffusion.diffusion_registry import PUBLIC_SITE_CODE
from scrinalia.domains.diffusion.models import DiffusionChannel, DiffusionChannelExclusion, DiffusionChannelScope
from scrinalia.domains.diffusion.publication_repository import DiffusionPublicationRepository

APPROVED = ArchiveReviewStatus.HUMAN_APPROVED


def a_channel(db: Session, code: str = PUBLIC_SITE_CODE, *, enabled: bool = True) -> DiffusionChannel:
    """The lifecycle row a scope's foreign key needs; the registry does not seed one."""
    row = DiffusionChannel(code=code, enabled=enabled)
    db.add(row)
    db.flush()
    return row


def a_node(
    db: Session,
    description_id: str,
    *,
    parent_id: str | None = None,
    approved: bool = True,
    title: str | None = None,
) -> ArchiveDocument:
    """A description with its materialised path and, by default, the approval the coverage requires."""
    parent_path = None
    if parent_id is not None:
        parent_path = db.scalar(select(ArchiveDocument.path).where(ArchiveDocument.description_id == parent_id))
    path = f"{parent_path}.{description_id}" if parent_path else description_id
    doc = ArchiveDocument(
        description_id=description_id,
        original_title=title or description_id,
        staging_content_hash=f"hash_{description_id}",
        parent_id=parent_id,
        path=path,
        review_status=APPROVED if approved else ArchiveReviewStatus.PENDING_AI,
    )
    db.add(doc)
    db.flush()
    return doc


def a_scope(
    db: Session,
    node_id: str,
    *,
    channel_code: str = PUBLIC_SITE_CODE,
    include_descendants: bool = True,
) -> DiffusionChannelScope:
    scope = DiffusionChannelScope(channel_code=channel_code, node_id=node_id, include_descendants=include_descendants)
    db.add(scope)
    db.flush()
    return scope


def an_exclusion(
    db: Session,
    node_id: str,
    *,
    channel_code: str = PUBLIC_SITE_CODE,
    include_descendants: bool = True,
) -> DiffusionChannelExclusion:
    row = DiffusionChannelExclusion(
        channel_code=channel_code,
        node_id=node_id,
        include_descendants=include_descendants,
        reason="pedido da instituição",
    )
    db.add(row)
    db.flush()
    return row


def a_revoked_scope(db: Session, node_id: str, *, channel_code: str = PUBLIC_SITE_CODE) -> DiffusionChannelScope:
    """A scope revoked by an earlier decision, for the undo's "changed since" case."""
    scope = a_scope(db, node_id, channel_code=channel_code)
    scope.revoked_at = datetime.now(UTC)
    db.flush()
    return scope


def coverage_of(db: Session, *description_ids: str) -> dict[str, list[str]]:
    """The channels each description is on, as the page and the public surface read it."""
    return DiffusionPublicationRepository(db).coverage_for(list(description_ids))
