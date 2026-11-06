"""Contract of the publication gesture: the preview, the batch and the undo (#251).

The write is one command with three moves — resolve, preview, apply — and the preview is a read: it
lists what each channel would gain or lose, and the token it returns is what the apply compares
against so the confirmation cannot run over a set that changed meanwhile. The batch is the
reversible unit (principle VI); the undo reports what it restored and what it skipped.

The channel is named by its code everywhere. The label is convenience for the screen, resolved from
the registry by the service, so a renamed channel does not rewrite the ledger.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from scrinalia.core.schemas import RequestModel


#: What the gesture does to the scopes it touches.
class PublicationAction(StrEnum):
    """The four writes a publication can be; the ledger stores the value verbatim."""

    PUBLISH = "PUBLISH"
    EXCLUDE = "EXCLUDE"
    REVOKE = "REVOKE"
    UNEXCLUDE = "UNEXCLUDE"


class PublicationMode(StrEnum):
    """Whether the gesture names a branch (a node) or a selection (up to 200 records)."""

    BRANCH = "BRANCH"
    RECORDS = "RECORDS"


#: The selection preview and apply share; the token binds the resolution to it.
class PublicationRequest(RequestModel):
    """
    One publication gesture, as the curator's page asks for it.

    ``PUBLISH`` creates the positive scopes, ``EXCLUDE`` the negative ones ("Manter privado" /
    "Retirar do canal"), ``REVOKE`` revokes a branch's positive scope ("Retirar o ramo") and
    ``UNEXCLUDE`` revokes a negative one. ``REVOKE``/``UNEXCLUDE`` are always a branch: a scope is
    attached to a node, and naming it by a selection would be ambiguous.

    ``include_descendants`` is what "o ramo" means; a selection publishes the records themselves.
    """

    action: PublicationAction
    channel_codes: list[str] = Field(min_length=1, max_length=20, description="Os canais do gesto, por código.")
    mode: PublicationMode = PublicationMode.BRANCH
    node_id: str | None = Field(default=None, description="O nó do ramo, quando o modo é BRANCH.")
    description_ids: list[str] = Field(
        default_factory=list,
        max_length=200,
        description="Os registros escolhidos, quando o modo é RECORDS (no máximo 200).",
    )
    include_descendants: bool = Field(default=True, description="Se o ramo inclui os descendentes.")
    note: str | None = Field(default=None, max_length=2000, description="Por que o curador decidiu; fica no lote.")

    @model_validator(mode="after")
    def _the_shape_matches_the_mode(self) -> PublicationRequest:
        """A branch names a node and no ids; a selection names ids and no node."""
        if self.mode is PublicationMode.BRANCH:
            if not self.node_id:
                raise ValueError("Informe o nó do ramo.")
            if self.description_ids:
                raise ValueError("Um ramo não leva uma seleção de registros.")
        else:
            if not self.description_ids:
                raise ValueError("Informe ao menos um registro.")
            if self.node_id:
                raise ValueError("Uma seleção não leva um nó de ramo.")
        if (
            self.action in (PublicationAction.REVOKE, PublicationAction.UNEXCLUDE)
            and self.mode is not PublicationMode.BRANCH
        ):
            raise ValueError("Revogar um escopo nomeia o ramo, não uma seleção de registros.")
        return self


class PublicationSampleDTO(RequestModel):
    """One record of the preview's sample: enough to recognise it, not a second list."""

    description_id: str
    title: str


class PublicationSkippedDTO(RequestModel):
    """
    Why the records under the selection are not in the eligible set, one count per reason.

    The buckets are disjoint and cover the candidate set: a record is not approved, or already
    covered, or excluded, or (for an exclusion) not covered. ``no_scope`` is the scope-level reason
    of a revoke or an unexclude: there is no active scope to undo.
    """

    not_approved: int = 0
    already_covered: int = 0
    excluded: int = 0
    not_covered: int = 0
    no_scope: int = 0
    missing: int = 0


class PublicationChannelPreviewDTO(RequestModel):
    """What one channel would receive, or lose, with the sample and the skip reasons."""

    code: str
    label: str
    eligible: int
    actionable: bool = Field(
        default=True,
        description="Se o gesto escreveria algo neste canal; falso para um escopo que já existe ou está bloqueado.",
    )
    sample: list[PublicationSampleDTO] = Field(default_factory=list)
    skipped: PublicationSkippedDTO = Field(default_factory=PublicationSkippedDTO)


class PublicationPreviewDTO(RequestModel):
    """
    The preview, with the token the apply has to echo.

    ``total_eligible`` is the sum across channels; a record on two channels counts twice, because
    the decision is per channel.
    """

    token: str
    expires_at: datetime
    channels: list[PublicationChannelPreviewDTO] = Field(default_factory=list)
    total_eligible: int = 0


class PublicationApplyRequest(RequestModel):
    """The confirmation: the same request the preview received, plus its token."""

    request: PublicationRequest
    token: str = Field(min_length=1)


class PublicationItemDTO(RequestModel):
    """One description in the publication lists, with the channels that carry it."""

    description_id: str
    title: str
    level: str | None = None
    document_date: date | None = None
    channels: list[str] = Field(default_factory=list)


class PublicationCountsDTO(RequestModel):
    """
    The header's four numbers.

    ``site`` counts the ``public_site`` coverage even while the channel is paused; ``in_review`` is
    everything the approval has not settled.
    """

    site: int = 0
    in_channels: int = 0
    approved_without_channel: int = 0
    in_review: int = 0
    enabled_channels: int = 0


class PublicationPageDTO(RequestModel):
    counts: PublicationCountsDTO
    items: list[PublicationItemDTO] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class PublicationScopeDTO(RequestModel):
    """
    One active scope, as "Publicações por ramo" shows it.

    ``covered_count`` is the scope's origin count (what a revoke would take away);
    ``approved_count`` is what the node holds, which is what explains an exclusion.
    """

    scope_id: int
    channel_code: str
    channel_label: str
    kind: Literal["INCLUSION", "EXCLUSION"]
    node_id: str
    node_title: str | None = None
    node_path: str
    include_descendants: bool
    note: str | None = None
    created_by: str | None = None
    created_at: datetime
    approved_count: int = 0
    covered_count: int = 0


class PublicationScopeListDTO(RequestModel):
    scopes: list[PublicationScopeDTO] = Field(default_factory=list)
    generated_at: datetime


class PublicationBatchDTO(RequestModel):
    """One gesture in the history: who, when, what, and whether it was undone."""

    batch_id: int
    action: PublicationAction
    channels: list[str] = Field(default_factory=list)
    applied_count: int = 0
    skipped_count: int = 0
    note: str | None = None
    requested_by: str | None = None
    created_at: datetime
    undone_at: datetime | None = None
    undone_by: str | None = None
    selection: dict[str, Any] = Field(default_factory=dict)


class PublicationBatchListDTO(RequestModel):
    batches: list[PublicationBatchDTO] = Field(default_factory=list)
    generated_at: datetime


class PublicationUndoDTO(RequestModel):
    """What the undo restored and what it left alone because it had changed since."""

    batch_id: int
    restored: int = 0
    skipped: int = 0
    undone_at: datetime
