"""Contract of the diffusion channel surface: the definitions, their lifecycle and their agenda.

The channel is an operational object, so the operator screen needs more than a name: the fields it
can edit, the run policy an export inherits, the schedule, and the last/active run once #212 lands.
These DTOs are that read model plus the two writes (configuration and agenda).

``config_fields`` is metadata *about* the channel's own Pydantic model, the same pattern the origins
page uses; a test pins the two sets equal, so a new setting cannot become a JSON box nobody knows how
to fill.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from scrinalia.core.schemas import RequestModel
from scrinalia.domains.archive.models.enums import WorkerRunStatus
from scrinalia.domains.diffusion.diffusion_registry import DiffusionCapability

#: The control a configuration field needs on the screen.
ConfigFieldKind = Literal["text", "number", "boolean"]


class DiffusionConfigFieldDTO(RequestModel):
    """One editable field of a channel's configuration, with its label and help."""

    name: str
    label: str
    help: str
    kind: ConfigFieldKind = "text"
    required: bool = False
    default: Any = None


class DiffusionScheduleDTO(RequestModel):
    """The channel's agenda, as the screen reads it; ``next_run_at`` is null while paused."""

    cron: str | None = None
    timezone: str | None = None
    next_run_at: datetime | None = None
    last_enqueued_at: datetime | None = None
    last_skipped_at: datetime | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class DiffusionChannelDTO(RequestModel):
    """
    One channel as the operator screen sees it.

    ``configured`` is ``True`` when a row exists; without it, "never added" and "paused" both read
    as ``enabled=false`` and the add picker cannot know what is still available. ``last_run`` and
    ``active_run`` are flattened so this contract does not import the run DTO; the run ledger and the
    ``channel_code`` axis are #212, so the fields are null until it lands.
    """

    code: str
    label: str
    description: str
    capability: DiffusionCapability
    configured: bool = Field(description="Se o canal foi adicionado (existe uma linha na tabela).")
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    config_fields: list[DiffusionConfigFieldDTO] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    schedule: DiffusionScheduleDTO | None = None
    last_run_id: int | None = None
    last_run_status: WorkerRunStatus | None = None
    last_run_at: datetime | None = None
    active_run_id: int | None = None
    active_run_status: WorkerRunStatus | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class DiffusionChannelListResponse(RequestModel):
    channels: list[DiffusionChannelDTO] = Field(default_factory=list)
    generated_at: datetime


class DiffusionChannelUpdateRequest(RequestModel):
    """
    The channel's lifecycle and configuration; the agenda has its own route.

    Every field is optional because a pause and a configuration save are different gestures: a
    ``PATCH`` with only ``enabled`` must not reset the configuration, and a form that saves only the
    config must not change the paused state. The service refuses an empty body.
    """

    enabled: bool | None = None
    config: dict[str, Any] | None = Field(
        default=None,
        description="A configuração do canal, validada pelo modelo dele (a identidade do site).",
    )
    options: dict[str, Any] | None = Field(
        default=None,
        description="A política de execução de um canal de exportação; vazia em um canal LIVE.",
    )


class DiffusionScheduleRequest(RequestModel):
    """The agenda: a five-field cron and an IANA zone. The channel's ``enabled`` is its own field."""

    cron: str = Field(min_length=1, max_length=120, description="Cinco campos: minuto, hora, dia, mês, semana.")
    timezone: str | None = Field(default=None, max_length=64, description="Zona IANA; o padrão é DEFAULT_TIMEZONE.")
