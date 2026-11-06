"""Resolves, previews and applies a publication; the batch is its reversible unit (ADR 0023).

The gesture is one command in three moves. ``preview`` resolves what each channel would gain or lose
and returns a token; ``apply`` re-resolves, compares the token and writes the scopes plus the batch;
``undo`` reverts the batch entry by entry and skips what changed since. Nothing is written by the
preview — principle VI — and the token is a *consistency* check, not a capability: it exists so the
confirmation cannot run over a set that changed between the two calls, and never to authorize the
write, which is the session's ``CURATE``.

The coverage itself is never computed here. The resolver asks ``archive_document_channels`` and
``archive_document_channel_exclusions`` — the one definition — and writes only the scopes the
predicate is derived from.

Two rules that the UI must be able to explain, and the service enforces:

* a positive and a negative scope on the same node and channel cannot both be active, so an exclusion
  on a directly published branch revokes that inclusion in the same batch;
* a branch scope may be created before it has an eligible record: that is how a child approved later
  enters the channel without a second human act.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.core.i18n import t
from scrinalia.domains.archive.domain.normalization import LIKE_ESCAPE, escape_like
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.diffusion.coverage import (
    ARCHIVE_DOCUMENT_CHANNEL_EXCLUSIONS,
    ARCHIVE_DOCUMENT_CHANNELS,
)
from scrinalia.domains.diffusion.diffusion_registry import get_channel_summary
from scrinalia.domains.diffusion.exceptions import (
    DiffusionChannelNotFoundError,
    InvalidDiffusionConfigError,
    PublicationBatchAlreadyUndoneError,
    PublicationBatchNotFoundError,
    PublicationNodeNotFoundError,
    PublicationPreviewStaleError,
    PublicationRefusedError,
)
from scrinalia.domains.diffusion.models import (
    DiffusionChannelExclusion,
    DiffusionChannelScope,
    DiffusionPublicationBatch,
    DiffusionPublicationEntry,
)
from scrinalia.domains.diffusion.publication_repository import DiffusionPublicationRepository, PublicationState
from scrinalia.domains.diffusion.publication_schemas import (
    PublicationAction,
    PublicationBatchDTO,
    PublicationBatchListDTO,
    PublicationChannelPreviewDTO,
    PublicationCountsDTO,
    PublicationItemDTO,
    PublicationMode,
    PublicationPageDTO,
    PublicationPreviewDTO,
    PublicationRequest,
    PublicationSampleDTO,
    PublicationScopeDTO,
    PublicationScopeListDTO,
    PublicationSkippedDTO,
    PublicationUndoDTO,
)
from scrinalia.domains.diffusion.repository import DiffusionChannelRepository
from scrinalia.domains.diffusion.scope_repository import (
    DiffusionScopeRepository,
    PublicationBatchRepository,
)

#: How long a preview's token stays usable. Short on purpose: the apply compares against a live
#: re-resolution, and a confirmation that sat overnight is a confirmation of another collection.
PREVIEW_TTL = timedelta(minutes=15)

#: How many records the preview shows as the sample; the count is the number the page prints.
SAMPLE_SIZE = 10


@dataclass
class _Resolution:
    """What one channel would receive, or lose, with the facts the preview and the apply share."""

    code: str
    label: str
    eligible: int = 0
    sample: list[PublicationSampleDTO] = field(default_factory=list)
    skipped: PublicationSkippedDTO = field(default_factory=PublicationSkippedDTO)
    digest: str = ""
    eligible_ids: list[str] = field(default_factory=list)
    actionable: bool = True
    inclusion: DiffusionChannelScope | None = None
    exclusion: DiffusionChannelExclusion | None = None


class DiffusionPublicationService:
    """The Difusão page's reads and its three writes."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.coverage = DiffusionPublicationRepository(db)
        self.scope_rows = DiffusionScopeRepository(db)
        self.batches = PublicationBatchRepository(db)
        self.channels = DiffusionChannelRepository(db)

    # --- reads -----------------------------------------------------------------------------------

    def summary(self) -> PublicationCountsDTO:
        """The header's four numbers, from one evaluation of the coverage."""
        counts = self.coverage.counts()
        return PublicationCountsDTO(
            site=counts.site,
            in_channels=counts.in_channels,
            approved_without_channel=counts.approved_without_channel,
            in_review=counts.in_review,
            enabled_channels=counts.enabled_channels,
        )

    def publications(
        self,
        *,
        state: PublicationState,
        node_id: str | None = None,
        channel_code: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PublicationPageDTO:
        """A page of covered (or approved-and-uncovered) descriptions, with the header counts."""
        rows, total = self.coverage.list_publications(
            state=state,
            node_id=node_id,
            channel_code=channel_code,
            limit=limit,
            offset=offset,
        )
        return PublicationPageDTO(
            counts=self.summary(),
            items=[
                PublicationItemDTO(
                    description_id=row.description_id,
                    title=row.title,
                    level=row.level,
                    document_date=row.document_date,
                    channels=list(row.channels),
                )
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    def scopes(self, channel_code: str | None = None) -> PublicationScopeListDTO:
        """The active positive and negative scopes, with their node and their counts."""
        return PublicationScopeListDTO(
            scopes=[
                PublicationScopeDTO(
                    scope_id=row.scope_id,
                    channel_code=row.channel_code,
                    channel_label=self._label(row.channel_code),
                    kind=row.kind,
                    node_id=row.node_id,
                    node_title=row.node_title,
                    node_path=row.node_path,
                    include_descendants=row.include_descendants,
                    note=row.note,
                    created_by=row.created_by,
                    created_at=row.created_at,
                    approved_count=row.approved_count,
                    covered_count=row.covered_count,
                )
                for row in self.coverage.list_scopes(channel_code)
            ],
            generated_at=datetime.now(UTC),
        )

    def history(self, limit: int = 50, offset: int = 0) -> PublicationBatchListDTO:
        """The batches, newest first."""
        batches, _total = self.batches.list(limit, offset)
        return PublicationBatchListDTO(
            batches=[self._batch_dto(batch) for batch in batches],
            generated_at=datetime.now(UTC),
        )

    # --- the preview -----------------------------------------------------------------------------

    def preview(self, request: PublicationRequest) -> PublicationPreviewDTO:
        """Resolves the selection per channel and returns the token the apply must echo."""
        channels = self._writable_channels(request.channel_codes)
        resolutions = [self._resolve(request, channel) for channel in channels]
        expires = datetime.now(UTC) + PREVIEW_TTL
        return PublicationPreviewDTO(
            token=self._token(expires, request, resolutions),
            expires_at=expires,
            channels=[self._channel_preview(resolution) for resolution in resolutions],
            total_eligible=sum(resolution.eligible for resolution in resolutions),
        )

    # --- the apply -------------------------------------------------------------------------------

    def apply(self, request: PublicationRequest, token: str, *, author: Author | None = None) -> PublicationBatchDTO:
        """
        Writes the scopes and the batch, after checking the selection is the previewed one.

        An expired or tampered token and a set that changed between the two calls are the same
        refusal: preview again. When no channel has anything to do, the answer is a sentence and no
        batch — a ledger of an empty gesture would be noise in the history.
        """
        expires = self._token_expiry(token)
        if expires < datetime.now(UTC):
            raise PublicationPreviewStaleError(
                t("A pré-visualização expirou. Pré-visualize de novo antes de confirmar.")
            )
        channels = self._writable_channels(request.channel_codes)
        resolutions = [self._resolve(request, channel) for channel in channels]
        expected = self._token(expires, request, resolutions)
        if not hmac.compare_digest(expected, token):
            raise PublicationPreviewStaleError(
                t("O conjunto mudou desde a pré-visualização. Pré-visualize de novo antes de confirmar.")
            )
        if not any(resolution.actionable for resolution in resolutions):
            raise PublicationRefusedError(
                t("Nada a fazer: os canais escolhidos já estão neste estado. Atualize a página.")
            )

        batch = self.batches.create(request.action, self._selection(request), request.note, author)
        applied = 0
        skipped = 0
        for resolution in resolutions:
            channel_applied, channel_skipped = self._write(request, resolution, batch, author)
            applied += channel_applied
            skipped += channel_skipped
        batch.applied_count = applied
        batch.skipped_count = skipped
        self.db.flush()
        return self._batch_dto(batch)

    # --- the undo --------------------------------------------------------------------------------

    def undo(self, batch_id: int, *, author: Author | None = None) -> PublicationUndoDTO:
        """
        Reverts the batch entry by entry.

        An entry is skipped when its scope changed since the batch: a created scope somebody else
        revoked, a revoked scope somebody else restored, or a reactivation that would collide with
        an active scope on the same node. The batch is closed even when everything was skipped —
        the attempt is part of the history, and a second undo is refused.
        """
        batch = self.batches.get(batch_id)
        if batch is None:
            raise PublicationBatchNotFoundError(t("Lote de publicação {batch_id} não encontrado.", batch_id=batch_id))
        if batch.undone_at is not None:
            raise PublicationBatchAlreadyUndoneError(
                t(
                    "O lote {batch_id} já foi desfeito; desfazer de novo reverteria decisões posteriores.",
                    batch_id=batch_id,
                )
            )
        restored = 0
        skipped = 0
        for entry in self.batches.entries(batch_id):
            if self._revert(entry, author):
                restored += 1
            else:
                skipped += 1
        self.batches.mark_undone(batch, author)
        self.db.flush()
        return PublicationUndoDTO(
            batch_id=batch_id,
            restored=restored,
            skipped=skipped,
            undone_at=batch.undone_at or datetime.now(UTC),
        )

    # --- resolution ------------------------------------------------------------------------------

    def _resolve(self, request: PublicationRequest, channel: str) -> _Resolution:
        """What this channel would gain or lose, and the digest the token binds."""
        resolution = _Resolution(code=channel, label=self._label(channel))
        if request.action in (PublicationAction.REVOKE, PublicationAction.UNEXCLUDE):
            self._resolve_scope_action(request, channel, resolution)
        else:
            self._resolve_selection(request, channel, resolution)
        resolution.digest = hashlib.sha256(",".join(sorted(resolution.eligible_ids)).encode()).hexdigest()
        return resolution

    def _resolve_selection(self, request: PublicationRequest, channel: str, resolution: _Resolution) -> None:
        """PUBLISH and EXCLUDE: classify the candidates and count what the cut leaves out."""
        node = None
        if request.mode is PublicationMode.BRANCH:
            assert request.node_id is not None
            node = self._node(request.node_id)
        conditions = self._candidate_conditions(request, node)
        covered = exists(
            select(1)
            .select_from(ARCHIVE_DOCUMENT_CHANNELS)
            .where(
                ARCHIVE_DOCUMENT_CHANNELS.c.description_id == ArchiveDocument.description_id,
                ARCHIVE_DOCUMENT_CHANNELS.c.channel_code == channel,
            )
        )
        excluded = exists(
            select(1)
            .select_from(ARCHIVE_DOCUMENT_CHANNEL_EXCLUSIONS)
            .where(
                ARCHIVE_DOCUMENT_CHANNEL_EXCLUSIONS.c.description_id == ArchiveDocument.description_id,
                ARCHIVE_DOCUMENT_CHANNEL_EXCLUSIONS.c.channel_code == channel,
            )
        )
        rows = self.db.execute(
            select(
                ArchiveDocument.description_id,
                func.coalesce(ArchiveDocument.final_title, ArchiveDocument.original_title),
                ArchiveDocument.path,
                ArchiveDocument.review_status,
                covered.label("covered"),
                excluded.label("excluded"),
            ).where(*conditions)
        ).all()

        eligible: list[tuple[str, str]] = []
        for description_id, title, _path, status, is_covered, is_excluded in rows:
            if request.action is PublicationAction.PUBLISH:
                if status != ArchiveReviewStatus.HUMAN_APPROVED:
                    resolution.skipped.not_approved += 1
                elif is_excluded:
                    resolution.skipped.excluded += 1
                elif is_covered:
                    resolution.skipped.already_covered += 1
                else:
                    eligible.append((description_id, title))
            else:
                if status != ArchiveReviewStatus.HUMAN_APPROVED:
                    resolution.skipped.not_approved += 1
                elif is_covered:
                    eligible.append((description_id, title))
                else:
                    resolution.skipped.not_covered += 1

        if request.mode is PublicationMode.RECORDS:
            found = {row[0] for row in rows}
            resolution.skipped.missing = len(set(request.description_ids) - found)

        eligible.sort(key=lambda row: row[1])
        resolution.eligible = len(eligible)
        resolution.eligible_ids = [description_id for description_id, _ in eligible]
        resolution.sample = [
            PublicationSampleDTO(description_id=row[0], title=row[1]) for row in eligible[:SAMPLE_SIZE]
        ]
        resolution.actionable = self._selection_is_actionable(request, channel, resolution, node)

    def _selection_is_actionable(
        self,
        request: PublicationRequest,
        channel: str,
        resolution: _Resolution,
        node: ArchiveDocument | None,
    ) -> bool:
        """
        Whether the gesture would write anything.

        A branch scope is actionable even with no eligible record — that is how a child approved
        later enters — unless the node is already published there or carries an exclusion. A
        selection needs at least one eligible record.
        """
        if request.action is PublicationAction.PUBLISH and request.mode is PublicationMode.BRANCH:
            assert node is not None
            blocked = self.scope_rows.active_inclusion(
                channel, node.description_id
            ) or self.scope_rows.active_exclusion(channel, node.description_id)
            if blocked is not None:
                resolution.eligible = 0
                resolution.eligible_ids = []
                resolution.sample = []
                return False
            return True
        return resolution.eligible > 0

    def _resolve_scope_action(self, request: PublicationRequest, channel: str, resolution: _Resolution) -> None:
        """REVOKE and UNEXCLUDE: the records the existing scope is the origin of."""
        assert request.node_id is not None
        node = self._node(request.node_id)
        if request.action is PublicationAction.REVOKE:
            resolution.inclusion = self.scope_rows.active_inclusion(channel, node.description_id)
            scope_id = resolution.inclusion.scope_id if resolution.inclusion is not None else None
            view = ARCHIVE_DOCUMENT_CHANNELS
        else:
            resolution.exclusion = self.scope_rows.active_exclusion(channel, node.description_id)
            scope_id = resolution.exclusion.scope_id if resolution.exclusion is not None else None
            view = ARCHIVE_DOCUMENT_CHANNEL_EXCLUSIONS
        if scope_id is None:
            resolution.skipped.no_scope = 1
            resolution.actionable = False
            return
        rows = self.db.execute(
            select(
                ArchiveDocument.description_id,
                func.coalesce(ArchiveDocument.final_title, ArchiveDocument.original_title),
            )
            .join(view, view.c.description_id == ArchiveDocument.description_id)
            .where(view.c.channel_code == channel, view.c.scope_id == scope_id)
            .order_by(func.coalesce(ArchiveDocument.final_title, ArchiveDocument.original_title))
        ).all()
        resolution.eligible = len(rows)
        resolution.eligible_ids = [row[0] for row in rows]
        resolution.sample = [PublicationSampleDTO(description_id=row[0], title=row[1]) for row in rows[:SAMPLE_SIZE]]
        resolution.actionable = True

    # --- the writes ------------------------------------------------------------------------------

    def _write(
        self,
        request: PublicationRequest,
        resolution: _Resolution,
        batch: DiffusionPublicationBatch,
        author: Author | None,
    ) -> tuple[int, int]:
        """Writes one channel's scopes and entries; returns the records applied and skipped."""
        if not resolution.actionable:
            return 0, 0
        if request.action is PublicationAction.PUBLISH:
            return self._publish(request, resolution, batch, author)
        if request.action is PublicationAction.EXCLUDE:
            return self._exclude(request, resolution, batch, author)
        if request.action is PublicationAction.REVOKE:
            return self._revoke(request, resolution, batch, author)
        return self._unexclude(request, resolution, batch, author)

    def _publish(
        self,
        request: PublicationRequest,
        resolution: _Resolution,
        batch: DiffusionPublicationBatch,
        author: Author | None,
    ) -> tuple[int, int]:
        """Creates the positive scopes: one for the branch, one direct per selected record."""
        if request.mode is PublicationMode.BRANCH:
            assert request.node_id is not None
            node = self._node(request.node_id)
            scope = self.scope_rows.create_inclusion(
                resolution.code,
                node.description_id,
                include_descendants=request.include_descendants,
                note=request.note,
                author=author,
            )
            self._entry(batch, scope, "INCLUSION", node, was_active=False, is_active=True)
            return resolution.eligible, 0
        created = 0
        for description_id in resolution.eligible_ids:
            node = self._node(description_id)
            scope = self.scope_rows.create_inclusion(
                resolution.code,
                node.description_id,
                include_descendants=False,
                note=request.note,
                author=author,
            )
            self._entry(batch, scope, "INCLUSION", node, was_active=False, is_active=True)
            created += 1
        return created, 0

    def _exclude(
        self,
        request: PublicationRequest,
        resolution: _Resolution,
        batch: DiffusionPublicationBatch,
        author: Author | None,
    ) -> tuple[int, int]:
        """Keeps the branch or the records private, revoking a direct inclusion when there is one."""
        if request.mode is PublicationMode.BRANCH:
            assert request.node_id is not None
            node = self._node(request.node_id)
            self._keep_private(
                resolution.code,
                node,
                include_descendants=request.include_descendants,
                reason=request.note,
                batch=batch,
                author=author,
            )
            return resolution.eligible, 0
        for description_id in resolution.eligible_ids:
            node = self._node(description_id)
            self._keep_private(
                resolution.code,
                node,
                include_descendants=False,
                reason=request.note,
                batch=batch,
                author=author,
            )
        return len(resolution.eligible_ids), 0

    def _keep_private(
        self,
        channel: str,
        node: ArchiveDocument,
        *,
        include_descendants: bool,
        reason: str | None,
        batch: DiffusionPublicationBatch,
        author: Author | None,
    ) -> None:
        """Revokes the direct inclusion and adds the exclusion; the pair on one node is temporary."""
        if self.scope_rows.active_exclusion(channel, node.description_id) is not None:
            return
        inclusion = self.scope_rows.active_inclusion(channel, node.description_id)
        if inclusion is not None:
            self.scope_rows.revoke_inclusion(inclusion, author)
            self._entry(batch, inclusion, "INCLUSION", node, was_active=True, is_active=False)
        exclusion = self.scope_rows.create_exclusion(
            channel,
            node.description_id,
            include_descendants=include_descendants,
            reason=reason,
            author=author,
        )
        self._entry(batch, exclusion, "EXCLUSION", node, was_active=False, is_active=True)

    def _revoke(
        self,
        request: PublicationRequest,
        resolution: _Resolution,
        batch: DiffusionPublicationBatch,
        author: Author | None,
    ) -> tuple[int, int]:
        """Revokes the branch's positive scope; what an ancestor covers stays covered."""
        assert request.node_id is not None
        node = self._node(request.node_id)
        scope = resolution.inclusion or self.scope_rows.active_inclusion(resolution.code, node.description_id)
        if scope is None:
            return 0, 0
        self.scope_rows.revoke_inclusion(scope, author)
        self._entry(batch, scope, "INCLUSION", node, was_active=True, is_active=False)
        return resolution.eligible, 0

    def _unexclude(
        self,
        request: PublicationRequest,
        resolution: _Resolution,
        batch: DiffusionPublicationBatch,
        author: Author | None,
    ) -> tuple[int, int]:
        """Revokes the branch's exclusion; the coverage it was hiding comes back on read."""
        assert request.node_id is not None
        node = self._node(request.node_id)
        exclusion = resolution.exclusion or self.scope_rows.active_exclusion(resolution.code, node.description_id)
        if exclusion is None:
            return 0, 0
        self.scope_rows.revoke_exclusion(exclusion, author)
        self._entry(batch, exclusion, "EXCLUSION", node, was_active=True, is_active=False)
        return resolution.eligible, 0

    # --- the undo's unit -------------------------------------------------------------------------

    def _revert(self, entry: DiffusionPublicationEntry, author: Author | None) -> bool:
        """Reverts one entry when its scope is still in the state the batch left; ``True`` if it did."""
        scope: DiffusionChannelScope | DiffusionChannelExclusion | None
        if entry.kind == "INCLUSION":
            scope = self.db.get(DiffusionChannelScope, entry.scope_id) if entry.scope_id is not None else None
        else:
            scope = self.db.get(DiffusionChannelExclusion, entry.scope_id) if entry.scope_id is not None else None
        if scope is None:
            return False
        if entry.is_active:
            if scope.revoked_at is not None:
                return False
            if entry.kind == "INCLUSION":
                self.scope_rows.revoke_inclusion(scope, author)  # type: ignore[arg-type]
            else:
                self.scope_rows.revoke_exclusion(scope, author)  # type: ignore[arg-type]
            return True
        if scope.revoked_at is None:
            return False
        conflict = (
            self.scope_rows.active_inclusion(entry.channel_code, entry.node_id)
            if entry.kind == "INCLUSION"
            else self.scope_rows.active_exclusion(entry.channel_code, entry.node_id)
        )
        if conflict is not None:
            return False
        if entry.kind == "INCLUSION":
            self.scope_rows.restore_inclusion(scope)  # type: ignore[arg-type]
        else:
            self.scope_rows.restore_exclusion(scope)  # type: ignore[arg-type]
        return True

    # --- the pieces ------------------------------------------------------------------------------

    def _writable_channels(self, codes: Sequence[str]) -> list[str]:
        """The channels the gesture may write to: configured, enabled and still in the registry."""
        channels: list[str] = []
        for code in dict.fromkeys(codes):
            get_channel_summary(code)
            row = self.channels.get(code)
            if row is None or not row.enabled:
                raise InvalidDiffusionConfigError(
                    t(
                        "O canal '{code}' não está configurado ou está pausado; ative-o antes de publicar.",
                        code=code,
                    )
                )
            channels.append(code)
        return sorted(channels)

    def _node(self, description_id: str) -> ArchiveDocument:
        """The branch or record the gesture names, or a 404 with the id."""
        node = self.db.get(ArchiveDocument, description_id)
        if node is None:
            raise PublicationNodeNotFoundError(
                t("A descrição '{description_id}' não existe no acervo.", description_id=description_id)
            )
        return node

    def _candidate_conditions(
        self, request: PublicationRequest, node: ArchiveDocument | None
    ) -> list[ColumnElement[bool]]:
        """The records the gesture looks at: the branch (node and descendants) or the selection."""
        if request.mode is PublicationMode.RECORDS:
            return [ArchiveDocument.description_id.in_(request.description_ids)]
        assert node is not None
        if not request.include_descendants:
            return [ArchiveDocument.description_id == node.description_id]
        return [
            or_(
                ArchiveDocument.description_id == node.description_id,
                ArchiveDocument.path.like(f"{escape_like(node.path)}.%", escape=LIKE_ESCAPE),
            )
        ]

    def _entry(
        self,
        batch: DiffusionPublicationBatch,
        scope: DiffusionChannelScope | DiffusionChannelExclusion,
        kind: str,
        node: ArchiveDocument,
        *,
        was_active: bool,
        is_active: bool,
    ) -> None:
        """Records the scope row the gesture touched, with the node snapshot the node may not keep."""
        self.batches.add_entry(
            batch,
            channel_code=scope.channel_code,
            kind=kind,
            scope_id=scope.scope_id,
            node_id=node.description_id,
            node_path=node.path,
            node_title=node.final_title or node.original_title,
            include_descendants=scope.include_descendants,
            was_active=was_active,
            is_active=is_active,
        )

    def _selection(self, request: PublicationRequest) -> dict[str, object]:
        """The gesture as the history explains it after the nodes moved."""
        return {
            "action": request.action.value,
            "mode": request.mode.value,
            "node_id": request.node_id,
            "description_ids": list(request.description_ids),
            "include_descendants": request.include_descendants,
        }

    def _channel_preview(self, resolution: _Resolution) -> PublicationChannelPreviewDTO:
        return PublicationChannelPreviewDTO(
            code=resolution.code,
            label=resolution.label,
            eligible=resolution.eligible,
            sample=list(resolution.sample),
            skipped=resolution.skipped,
            actionable=resolution.actionable,
        )

    def _batch_dto(self, batch: DiffusionPublicationBatch) -> PublicationBatchDTO:
        return PublicationBatchDTO(
            batch_id=batch.batch_id,
            action=PublicationAction(batch.action),
            channels=self.batches.channels_of(batch.batch_id),
            applied_count=batch.applied_count,
            skipped_count=batch.skipped_count,
            note=batch.note,
            requested_by=batch.requested_by,
            created_at=batch.created_at,
            undone_at=batch.undone_at,
            undone_by=batch.undone_by,
            selection=dict(batch.selection or {}),
        )

    def _label(self, code: str) -> str:
        """The channel's label, or its code when the definition left the registry."""
        try:
            return get_channel_summary(code).label
        except DiffusionChannelNotFoundError:
            return code

    # --- the token: a consistency check, not a capability ----------------------------------------

    @staticmethod
    def _canonical(request: PublicationRequest) -> str:
        """The request as a stable string; the token binds to it so a changed body is a refusal."""
        return json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _token(expires: datetime, request: PublicationRequest, resolutions: list[_Resolution]) -> str:
        """
        The token: the expiry and the digest of the request plus each channel's resolved set.

        Not an HMAC: there is no application signing secret, and the token is not a capability —
        the write is authorized by the session's ``CURATE``. What it guarantees is that the
        confirmation runs over the set the curator saw, or refuses.
        """
        sets = "|".join(f"{resolution.code}:{resolution.digest}" for resolution in resolutions)
        payload = f"{DiffusionPublicationService._canonical(request)}|{sets}"
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return f"{int(expires.timestamp())}.{digest}"

    @staticmethod
    def _token_expiry(token: str) -> datetime:
        """The expiry the token carries; a malformed token is a stale preview."""
        try:
            stamp, _digest = token.split(".", 1)
            return datetime.fromtimestamp(int(stamp), UTC)
        except (ValueError, TypeError) as exc:
            raise PublicationPreviewStaleError(
                t("A pré-visualização é inválida. Pré-visualize de novo antes de confirmar.")
            ) from exc
