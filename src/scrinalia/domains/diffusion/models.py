from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scrinalia.core.base import Base


class DiffusionChannel(Base):
    """
    One diffusion channel this installation added, with its lifecycle, its configuration and its
    agenda.

    The *definition* of a channel — its capability, the shape of its configuration and the labels of
    its fields — lives in code (``domains/diffusion/diffusion_registry.py``). This table is what an
    operator changes without a deploy: whether the channel is enabled, the presentation identity or
    destination it carries, the run policy an export inherits, and the cron/zone of its agenda.

    ``code`` is the foreign key in spirit to the code registry, without a database foreign key:
    channels are code, and a row whose code left the registry stays readable — it simply cannot be
    used. ``enabled=false`` is a pause; a missing row is "never added", which is what ``configured``
    on the DTO distinguishes (ADR 0023).

    There is **no seed**: a fresh installation has no channel, and the operator page's empty state
    is real.
    """

    __tablename__ = "diffusion_channels"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    #: The channel's own configuration (the public site's presentation identity, a dataset's
    #: destination). Validated by the channel's ``config_model`` on every read and write; never a
    #: place for a secret.
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: The run policy an export channel inherits (formats, destination, limits). Empty for a
    #: ``LIVE`` channel, which has no run.
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: The five-field cron, evaluated in ``timezone``. ``NULL`` means the channel has no agenda and
    #: is only reachable through a manual export run.
    cron: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: The account behind the name above; ``SET NULL`` so a deactivated account keeps its name on
    #: the decision, like every other author link in the schema.
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # The scheduler's due query: enabled channels with an agenda whose next run is due.
        Index("ix_diffusion_channel_next_run_at", "next_run_at"),
    )
