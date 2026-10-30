"""Reads the coverage view and the scope ledger; the caller owns the transaction.

The coverage is **not** computed here: it is the view (``coverage.py``), and these queries read it.
That is the point of the view — the public search, the curator's page, the counts and the export all
ask the same question, and a second implementation would answer it differently the first time a
scope, a path or the approval rule moved.

The read models are plain dataclasses and not the API's DTOs: the API layer decides what the contract
exposes (and what the public projection may not), and the tests of the predicate do not need a
Pydantic model to prove a record is covered.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from sqlalchemy import ColumnElement, and_, func, or_, select, true
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased

from scrinalia.domains.archive.domain.normalization import LIKE_ESCAPE, escape_like
from scrinalia.domains.archive.models import ArchiveDescriptionLevel, ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.diffusion.coverage import ARCHIVE_DOCUMENT_CHANNELS as COVERAGE
from scrinalia.domains.diffusion.diffusion_registry import PUBLIC_SITE_CODE
from scrinalia.domains.diffusion.models import (
    DiffusionChannel,
    DiffusionChannelExclusion,
    DiffusionChannelScope,
)

#: Which list the curator's page is asking for: what is on a channel, or what is approved and is not.
PublicationState = Literal["covered", "uncovered"]

#: One of the two scope tables, as the read below treats them. The two are mirrors (ADR 0023).
ScopeModel = type[DiffusionChannelScope] | type[DiffusionChannelExclusion]


@dataclass(frozen=True)
class CoverageCounts:
    """
    The four numbers the page's header and the home card read, from one definition.

    ``site`` counts the ``public_site`` coverage even while the channel is paused: the pause is the
    operator's, and the curator's set did not change. ``in_channels`` counts distinct descriptions,
    not rows — a record on two channels is one record.
    """

    site: int
    in_channels: int
    approved_without_channel: int
    in_review: int
    enabled_channels: int


@dataclass(frozen=True)
class PublicationRow:
    """One description as the publication lists show it, with the channels that carry it."""

    description_id: str
    title: str
    level: str | None
    document_date: date | None
    channels: tuple[str, ...]


@dataclass(frozen=True)
class ScopeRow:
    """
    One scope as "Publicações por ramo" shows it.

    ``covered_count`` is the scope's **origin** count — the descriptions whose nearest covering
    scope is this one — because that is what a revoke would take away. ``approved_count`` is the
    approved descriptions under the node, the number the exclusion's row shows (an exclusion has no
    origin count: nothing is published by it).
    """

    scope_id: int
    channel_code: str
    kind: Literal["INCLUSION", "EXCLUSION"]
    node_id: str
    node_title: str | None
    node_path: str
    include_descendants: bool
    note: str | None
    created_by: str | None
    created_at: datetime
    approved_count: int
    covered_count: int


def _covered(channel_code: str | None = None) -> ColumnElement[bool]:
    """``EXISTS`` over the coverage view; the one way this module asks whether a record is exposed."""
    condition = COVERAGE.c.description_id == ArchiveDocument.description_id
    if channel_code is not None:
        condition = and_(condition, COVERAGE.c.channel_code == channel_code)
    return select(1).select_from(COVERAGE).where(condition).exists()


def _escaped_path(path: str) -> str:
    """The escaped prefix of a node's path, so the id's wildcards stay characters (``escape_like``)."""
    return f"{escape_like(path)}.%"


class DiffusionPublicationRepository:
    """The reads behind the Difusão page, the counts and the future export (#214)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- the counts ------------------------------------------------------------------------------

    def counts(self) -> CoverageCounts:
        """
        The four numbers in **one** evaluation of the view plus one of the documents.

        ``approved_without_channel`` is ``approved - in_channels`` and not a third query: the
        coverage only carries approved descriptions, so the difference is exactly the approved
        records with no channel. On the seeded collection that is the difference between ~600 ms and
        ~200 ms at 48 050 descriptions, and the header is read on every visit to the page.
        """
        coverage = (
            select(
                func.count(func.distinct(COVERAGE.c.description_id)).label("in_channels"),
                func.count().filter(COVERAGE.c.channel_code == PUBLIC_SITE_CODE).label("site"),
            )
            .select_from(COVERAGE)
            .subquery()
        )
        documents = (
            select(
                func.count().label("total"),
                func.count()
                .filter(ArchiveDocument.review_status == ArchiveReviewStatus.HUMAN_APPROVED)
                .label("approved"),
            )
            .select_from(ArchiveDocument)
            .subquery()
        )
        enabled_channels = (
            select(func.count()).select_from(DiffusionChannel).where(DiffusionChannel.enabled.is_(True))
        ).scalar_subquery()
        row = self.db.execute(
            select(coverage.c.in_channels, coverage.c.site, documents.c.approved, documents.c.total, enabled_channels)
            # Both subqueries answer one row; the cross join is the one-row product, spelled so
            # SQLAlchemy does not read it as a forgotten join condition.
            .select_from(coverage)
            .join(documents, true())
        ).one()
        in_channels = int(row[0] or 0)
        approved = int(row[2] or 0)
        total = int(row[3] or 0)
        return CoverageCounts(
            site=int(row[1] or 0),
            in_channels=in_channels,
            approved_without_channel=approved - in_channels,
            in_review=total - approved,
            enabled_channels=int(row[4] or 0),
        )

    # --- the lists -------------------------------------------------------------------------------

    def list_publications(
        self,
        *,
        state: PublicationState,
        node_id: str | None = None,
        channel_code: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PublicationRow], int]:
        """
        A page of covered (or approved-and-uncovered) descriptions, with their channels.

        ``node_id`` filters the branch the same way the collection's ``ancestor_id`` does, and the
        path is escaped: an id is free text, and ``fundo_a`` must not match ``fundoXa``.
        """
        conditions: list[ColumnElement[bool]] = []
        if node_id is not None:
            path = self.db.scalar(select(ArchiveDocument.path).where(ArchiveDocument.description_id == node_id))
            if path is None:
                return [], 0
            conditions.append(
                or_(
                    ArchiveDocument.description_id == node_id,
                    ArchiveDocument.path.like(_escaped_path(path), escape=LIKE_ESCAPE),
                )
            )
        if state == "covered":
            conditions.append(_covered(channel_code))
        else:
            conditions.append(ArchiveDocument.review_status == ArchiveReviewStatus.HUMAN_APPROVED)
            conditions.append(~_covered(channel_code))

        title = func.coalesce(ArchiveDocument.final_title, ArchiveDocument.original_title)
        total = int(self.db.scalar(select(func.count()).select_from(ArchiveDocument).where(*conditions)) or 0)
        rows = self.db.execute(
            select(
                ArchiveDocument.description_id,
                title,
                ArchiveDescriptionLevel.name,
                ArchiveDocument.document_date,
            )
            .outerjoin(ArchiveDescriptionLevel, ArchiveDocument.level_id == ArchiveDescriptionLevel.level_id)
            .where(*conditions)
            .order_by(title, ArchiveDocument.description_id)
            .limit(limit)
            .offset(offset)
        ).all()
        channels = self.coverage_for([row[0] for row in rows])
        return (
            [
                PublicationRow(
                    description_id=row[0],
                    title=row[1],
                    level=row[2],
                    document_date=row[3],
                    channels=tuple(channels.get(row[0], ())),
                )
                for row in rows
            ],
            total,
        )

    def coverage_for(self, description_ids: Sequence[str]) -> dict[str, list[str]]:
        """
        The channels each of these descriptions is on, ordered by code.

        One query for a page, never one per row: the dossier and the collection read ``channels`` on
        every document, and a per-row query would put the view on the N+1 path.
        """
        if not description_ids:
            return {}
        rows = self.db.execute(
            select(COVERAGE.c.description_id, COVERAGE.c.channel_code)
            .where(COVERAGE.c.description_id.in_(description_ids))
            .order_by(COVERAGE.c.description_id, COVERAGE.c.channel_code)
        ).all()
        coverage: dict[str, list[str]] = {}
        for description_id, channel_code in rows:
            coverage.setdefault(description_id, []).append(channel_code)
        return coverage

    # --- the scopes ------------------------------------------------------------------------------

    def list_scopes(self, channel_code: str | None = None) -> list[ScopeRow]:
        """
        The active positive and negative scopes, with the node, the author and the two counts.

        ``covered_count`` comes from the view grouped by origin scope; it is the number a revoke has
        to show. ``approved_count`` is what the node holds, which is what explains an exclusion.
        """
        covered = dict(self.db.execute(select(COVERAGE.c.scope_id, func.count()).group_by(COVERAGE.c.scope_id)).all())
        sources: tuple[tuple[ScopeModel, Literal["INCLUSION", "EXCLUSION"], InstrumentedAttribute[str | None]], ...] = (
            (DiffusionChannelScope, "INCLUSION", DiffusionChannelScope.note),
            (DiffusionChannelExclusion, "EXCLUSION", DiffusionChannelExclusion.reason),
        )
        rows: list[ScopeRow] = []
        for scope, kind, text_column in sources:
            rows.extend(self._scope_rows(scope, kind, text_column, channel_code, covered))
        rows.sort(key=lambda row: (row.channel_code, row.kind, row.node_path))
        return rows

    def _scope_rows(
        self,
        scope: ScopeModel,
        kind: Literal["INCLUSION", "EXCLUSION"],
        text_column: InstrumentedAttribute[str | None],
        channel_code: str | None,
        covered: dict[int, int],
    ) -> list[ScopeRow]:
        """One scope table's active rows, with the node and the counts the page prints."""
        node = aliased(ArchiveDocument)
        approved = self._approved_counts(scope)
        statement = (
            select(
                scope.scope_id,
                scope.channel_code,
                scope.node_id,
                scope.include_descendants,
                text_column,
                scope.created_by,
                scope.created_at,
                func.coalesce(node.final_title, node.original_title),
                node.path,
            )
            .join(node, node.description_id == scope.node_id)
            .where(scope.revoked_at.is_(None))
            .order_by(scope.channel_code, scope.created_at)
        )
        if channel_code is not None:
            statement = statement.where(scope.channel_code == channel_code)
        return [
            ScopeRow(
                scope_id=row[0],
                channel_code=row[1],
                kind=kind,
                node_id=row[2],
                include_descendants=row[3],
                note=row[4],
                created_by=row[5],
                created_at=row[6],
                node_title=row[7],
                node_path=row[8],
                approved_count=approved.get(row[0], 0),
                covered_count=covered.get(row[0], 0) if kind == "INCLUSION" else 0,
            )
            for row in self.db.execute(statement).all()
        ]

    def _approved_counts(self, scope: ScopeModel) -> dict[int, int]:
        """
        Approved descriptions under each active node of one scope table, in one grouped query.

        The branch is expanded the way the coverage view does it — the materialised path split into
        its ids — and not with a ``LIKE`` per scope: on the seeded 48 050-description collection the
        ``LIKE`` version took **753 ms** for the whole scope list, because the pattern is built per
        scope and the planner scans the documents once per scope.
        """
        ancestry = (
            select(
                ArchiveDocument.description_id,
                func.unnest(func.string_to_array(ArchiveDocument.path, ".")).label("node_id"),
            )
            .where(ArchiveDocument.review_status == ArchiveReviewStatus.HUMAN_APPROVED)
            .subquery()
        )
        return dict(
            self.db.execute(
                select(scope.scope_id, func.count(ancestry.c.description_id))
                .select_from(scope)
                .join(ancestry, ancestry.c.node_id == scope.node_id)
                .where(
                    scope.revoked_at.is_(None),
                    or_(scope.include_descendants, scope.node_id == ancestry.c.description_id),
                )
                .group_by(scope.scope_id)
            ).all()
        )
