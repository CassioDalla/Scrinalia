from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
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


class _DiffusionScope(Base):
    """
    The shape the positive and the negative scope share (ADR 0023).

    A scope is the curator's decision "this branch/record goes to this channel" (positive) or "this
    branch/record stays out of it" (negative). It is **not** a per-record assignment: the coverage of
    its approved descendants is a read of the materialised ``path``, so a child approved later enters
    the channel without a second human act and without a worker.

    The row is never deleted: revoking is ``revoked_at``, because "who published this record" is
    answered by the scope's author and the batch ledger, and a hard delete would erase the record
    that the decision was ever taken. The partial unique index makes a second active scope on the
    same node and channel impossible.

    ``node_id`` is the description's key and cascades with it: a deleted node takes its scopes, and
    the batch ledger keeps the snapshot. ``channel_code`` points at the lifecycle row (the operator
    must have added the channel before the curator can publish to it).
    """

    __abstract__ = True

    scope_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_code: Mapped[str] = mapped_column(
        ForeignKey("diffusion_channels.code", ondelete="RESTRICT"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("archive_documents.description_id", ondelete="CASCADE"), nullable=False
    )
    include_descendants: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    revoked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )


class DiffusionChannelScope(_DiffusionScope):
    """
    The positive scope: the branch or record this channel carries.

    ``include_descendants=false`` is the direct publication of one record; ``true`` is "the ramo",
    whose approved descendants are covered on read. Two active scopes on the same node and channel
    are impossible by index, so "already covered" is a fact the preview can read instead of a
    service convention.
    """

    __tablename__ = "diffusion_channel_scopes"

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "uq_diffusion_channel_scope_active",
            "channel_code",
            "node_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # The view reads the active scopes per channel; the partial index keeps the read proportional
        # to what is published, not to what was ever published.
        Index("ix_diffusion_channel_scope_channel", "channel_code", postgresql_where=text("revoked_at IS NULL")),
        Index("ix_diffusion_channel_scope_node", "node_id"),
    )


class DiffusionChannelExclusion(_DiffusionScope):
    """
    The negative scope: the branch or record this channel must not expose.

    It has the positive scope's shape plus the ``reason`` the curator gives. The predicate gives it
    the last word: an exclusion on a child removes it from a channel its fundo publishes, and an
    exclusion on a subtree removes all of it. The service refuses an exclusion and an inclusion on
    the same node, so the pair the predicate would have to explain does not exist.
    """

    __tablename__ = "diffusion_channel_exclusions"

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "uq_diffusion_channel_exclusion_active",
            "channel_code",
            "node_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_diffusion_channel_exclusion_channel", "channel_code", postgresql_where=text("revoked_at IS NULL")),
        Index("ix_diffusion_channel_exclusion_node", "node_id"),
    )


class DiffusionPublicationBatch(Base):
    """
    One publication gesture, with the ledger that makes it reversible (principle VI).

    ``selection`` is the human decision as it was resolved — the mode (a ramo or a selection), the
    node or the ids and the channels — so the history can explain the batch after the nodes moved.
    ``action`` names the gesture; the entries name what each row did. ``undone_*`` is written by the
    undo and is never cleared: a batch is undone once, and a second attempt is refused.

    The counts are stored instead of recomputed because the set the batch resolved is not the set a
    later read would resolve: the records approved after it are not its doing.
    """

    __tablename__ = "diffusion_publication_batches"

    batch_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    selection: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    undone_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('PUBLISH', 'EXCLUDE', 'REVOKE', 'UNEXCLUDE')",
            name="chk_diffusion_publication_batch_action",
        ),
    )


class DiffusionPublicationEntry(Base):
    """
    One scope row a batch created or revoked, with the snapshot that survives the node.

    ``node_id``/``node_path``/``node_title`` are **not** foreign keys: the node can be deleted or
    moved after the batch, and the ledger still has to say what the decision was about. ``scope_id``
    is a soft link for the same reason — a revoked scope stays, but the entry must not depend on it.
    ``was_active`` and ``is_active`` are the state before and after, which is what makes the undo able
    to restore what is unchanged and report the rest.
    """

    __tablename__ = "diffusion_publication_entries"

    entry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("diffusion_publication_batches.batch_id", ondelete="CASCADE"), nullable=False
    )
    channel_code: Mapped[str] = mapped_column(String(50), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    scope_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    node_id: Mapped[str] = mapped_column(String(50), nullable=False)
    node_path: Mapped[str] = mapped_column(Text, nullable=False)
    node_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    include_descendants: Mapped[bool] = mapped_column(Boolean, nullable=False)
    was_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('INCLUSION', 'EXCLUSION')", name="chk_diffusion_publication_entry_kind"),
        Index("ix_diffusion_publication_entry_batch", "batch_id"),
    )
