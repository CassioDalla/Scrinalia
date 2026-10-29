"""The diffusion channel's read model, its writes and the public site identity.

This is the service behind the operator page (#213) and behind ``GET /api/v1/public/site``. It owns
three things the panel needs in one answer: the registry definition, the effective configuration and
the agenda. The two writes are the channel's lifecycle/configuration and its schedule.

The configuration is validated by the channel's own Pydantic model on every read and write, exactly
like an origin's: a typo is a 422 with a sentence, never a JSONB the next run discovers at 02:00. The
``LIVE``/``EXPORT`` split decides what has an agenda: the public site is read on every request and
has no run, so a schedule or a non-empty option set on it is a refusal, not a no-op.

The record a channel exposes is **not** here: that is the publication scope of #251. This service
knows only where the archive can go, never which description goes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.core.config import get_settings
from scrinalia.core.i18n import t
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunDTO, WorkerRunRepository
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger
from scrinalia.domains.archive.workers.schedule import (
    InvalidCronError,
    InvalidTimezoneError,
    next_occurrence,
    validate_cron,
    validate_timezone,
)
from scrinalia.domains.diffusion.diffusion_registry import (
    CHANNELS,
    DiffusionCapability,
    DiffusionChannelSummary,
    PublicSiteConfig,
    adapter_module,
    get_channel_summary,
)
from scrinalia.domains.diffusion.exceptions import (
    DiffusionChannelNotFoundError,
    InvalidDiffusionConfigError,
    PublicSiteNotConfiguredError,
)
from scrinalia.domains.diffusion.models import DiffusionChannel
from scrinalia.domains.diffusion.repository import DiffusionChannelRepository
from scrinalia.domains.diffusion.schemas import (
    DiffusionChannelDTO,
    DiffusionChannelListResponse,
    DiffusionChannelUpdateRequest,
    DiffusionConfigFieldDTO,
    DiffusionScheduleDTO,
    DiffusionScheduleRequest,
)


class DiffusionChannelService:
    """The operator screen's read model, its writes and the channel's manual run."""

    def __init__(self, db: Session, ledger: WorkerRunLedger | None = None) -> None:
        self.db = db
        self.channels = DiffusionChannelRepository(db)
        # The ledger writes through its own committed session, so the QUEUED row is durable before
        # the response and visible to a runner that claims it (ADR 0014).
        self.ledger = ledger or WorkerRunLedger()

    # --- reads -----------------------------------------------------------------------------------

    def list_channels(self) -> DiffusionChannelListResponse:
        """
        Every definition the package ships, configured or not.

        A definition without a row is the add picker's row (``configured=false``); a definition with
        one is the configured card. The list is every definition on purpose: the picker filters the
        flag instead of the API keeping a second "available" list that could disagree.
        """
        rows = {row.code: row for row in self.channels.list_all()}
        runs = WorkerRunRepository(self.db)
        last = runs.last_diffusion_by_channel()
        active = runs.active_diffusion_by_channel()
        return DiffusionChannelListResponse(
            channels=[
                self._dto(summary, rows.get(summary.code), last=last.get(summary.code), active=active.get(summary.code))
                for summary in CHANNELS.values()
            ],
            generated_at=datetime.now(UTC),
        )

    def get_channel(self, code: str) -> DiffusionChannelDTO:
        """One definition with its lifecycle; an unknown code answers 404 with the known ones."""
        runs = WorkerRunRepository(self.db)
        return self._dto(
            get_channel_summary(code),
            self.channels.get(code),
            last=runs.last_diffusion_by_channel().get(code),
            active=runs.active_diffusion_by_channel().get(code),
        )

    # --- writes ----------------------------------------------------------------------------------

    def update_channel(
        self,
        code: str,
        request: DiffusionChannelUpdateRequest,
        *,
        author: Author | None = None,
    ) -> DiffusionChannelDTO:
        """
        Saves the lifecycle and the channel's own configuration; the agenda has its own route.

        Every field is optional because a pause and a save are different gestures: a ``PATCH`` with
        only ``enabled`` preserves the configuration, and a form that saves only the config preserves
        the paused state. The service refuses an empty body.
        """
        summary = get_channel_summary(code)
        channel = self.channels.get(code)
        if request.enabled is None and request.config is None and request.options is None:
            raise InvalidDiffusionConfigError(t("Informe o que mudar no canal '{code}'.", code=code))

        config = None
        if request.config is not None:
            config = self._validated_config(summary, request.config)
        elif channel is None:
            raise InvalidDiffusionConfigError(
                t("O canal '{code}' ainda não está configurado. Salve a configuração primeiro.", code=code)
            )

        options = None
        if request.options is not None:
            if summary.capability is DiffusionCapability.LIVE and request.options:
                raise InvalidDiffusionConfigError(
                    t("O canal '{code}' é lido a cada requisição e não tem opções de execução.", code=code)
                )
            options = dict(request.options)

        channel = self.channels.upsert_settings(
            code,
            enabled=request.enabled,
            config=config,
            options=options,
            author=author,
        )
        # A paused channel has no next run; enabling it again recomputes from the same cron.
        if request.enabled is not None and not request.enabled and channel.cron:
            channel.next_run_at = None
        elif request.enabled and channel.cron and channel.next_run_at is None:
            channel.next_run_at = next_occurrence(
                channel.cron,
                channel.timezone or get_settings().DEFAULT_TIMEZONE,
                datetime.now(UTC),
            )
        self.db.flush()
        return self.get_channel(code)

    def set_schedule(
        self,
        code: str,
        request: DiffusionScheduleRequest,
        *,
        author: Author | None = None,
    ) -> DiffusionChannelDTO:
        """Validates the cron and the zone, computes the first run, and stores the agenda."""
        summary = get_channel_summary(code)
        if summary.capability is DiffusionCapability.LIVE:
            raise InvalidDiffusionConfigError(
                t("O canal '{code}' é o site público: ele é lido a cada requisição e não tem agenda.", code=code)
            )
        channel = self.channels.get(code)
        if channel is None:
            raise DiffusionChannelNotFoundError(
                t("O canal '{code}' ainda não está configurado. Salve a configuração antes da agenda.", code=code)
            )

        zone = request.timezone or get_settings().DEFAULT_TIMEZONE
        try:
            cron = validate_cron(request.cron)
            timezone = validate_timezone(zone)
        except InvalidCronError as exc:
            raise InvalidDiffusionConfigError(
                t("Agenda inválida: o cron precisa de cinco campos (minuto, hora, dia do mês, mês e dia da semana).")
            ) from exc
        except InvalidTimezoneError as exc:
            raise InvalidDiffusionConfigError(
                t("Agenda inválida: '{zone}' não é um fuso IANA conhecido.", zone=zone)
            ) from exc

        next_run_at = next_occurrence(cron, timezone, datetime.now(UTC)) if channel.enabled else None
        self.channels.set_schedule(code, cron=cron, timezone=timezone, next_run_at=next_run_at, author=author)
        self.db.flush()
        return self.get_channel(code)

    def clear_schedule(self, code: str, *, author: Author | None = None) -> DiffusionChannelDTO:
        """Removes the agenda; the channel keeps its configuration and the runs it already created."""
        summary = get_channel_summary(code)
        if summary.capability is DiffusionCapability.LIVE:
            raise InvalidDiffusionConfigError(
                t("O canal '{code}' é o site público: ele é lido a cada requisição e não tem agenda.", code=code)
            )
        if self.channels.get(code) is None:
            raise DiffusionChannelNotFoundError(t("O canal '{code}' não está configurado.", code=code))
        self.channels.set_schedule(code, cron=None, timezone=None, next_run_at=None, author=author)
        self.db.flush()
        return self.get_channel(code)

    # --- the manual run --------------------------------------------------------------------------

    def trigger(self, code: str, *, requested_by: Author | None = None) -> WorkerRunDTO:
        """
        Queues one export run of the channel and answers the ``QUEUED`` row.

        The channel is the **selector** of the run, which is why this route exists instead of the
        generic worker one: a ``WorkerRunRequest`` has no channel to name. The row carries the
        channel as its axis and pins the channel's saved run policy in ``request``; the runner
        re-reads the channel row at execution, exactly like the ingestion run resolves its origin.

        A ``LIVE`` channel has no run, a paused channel does not export, and a channel without an
        adapter is refused here rather than queued to fail: the operator reads the sentence now, and
        the ledger does not collect a failure the operator cannot fix.
        """
        summary = get_channel_summary(code)
        channel = self.channels.get(code)
        if channel is None:
            raise DiffusionChannelNotFoundError(
                t("O canal '{code}' ainda não está configurado. Salve a configuração antes de executar.", code=code)
            )
        if summary.capability is not DiffusionCapability.EXPORT:
            raise InvalidDiffusionConfigError(
                t("O canal '{code}' é lido a cada requisição e não tem execução.", code=code)
            )
        if not channel.enabled:
            raise InvalidDiffusionConfigError(t("O canal '{code}' está pausado; ative-o antes de executar.", code=code))
        adapter_module(summary)

        return self.ledger.enqueue(
            "diffusion",
            requested_by=requested_by,
            engine_name=None,
            preset=None,
            config={},
            channel_code=code,
            request={"options": dict(channel.options or {})},
        )

    # --- the public site identity ----------------------------------------------------------------

    def public_site(self) -> PublicSiteConfig:
        """
        The ``public_site`` identity the app (#46) reads before its first document query.

        A missing row and a paused channel both answer 404: the site is not configured as far as a
        visitor is concerned, and the operator sees the pause on the page instead.
        """
        channel = self.channels.get("public_site")
        if channel is None or not channel.enabled:
            raise PublicSiteNotConfiguredError(t("O site público ainda não está configurado nesta instalação."))
        try:
            return PublicSiteConfig.model_validate(dict(channel.config or {}))
        except ValidationError as exc:
            raise InvalidDiffusionConfigError(t("Configuração inválida do site público: {exc}", exc=exc)) from exc

    # --- the DTO ---------------------------------------------------------------------------------

    def _dto(
        self,
        summary: DiffusionChannelSummary,
        channel: DiffusionChannel | None,
        *,
        last: WorkerRunDTO | None = None,
        active: WorkerRunDTO | None = None,
    ) -> DiffusionChannelDTO:
        return DiffusionChannelDTO(
            code=summary.code,
            label=summary.label,
            description=summary.description,
            capability=summary.capability,
            configured=channel is not None,
            enabled=channel.enabled if channel is not None else False,
            config=self._config_of(summary, channel),
            config_fields=[
                DiffusionConfigFieldDTO(
                    name=field.name,
                    label=field.label,
                    help=field.help,
                    kind=field.kind,
                    required=field.required,
                    default=field.default,
                )
                for field in summary.config_fields
            ],
            options=dict(channel.options or {}) if channel is not None else {},
            schedule=self._schedule_of(channel),
            last_run_id=last.run_id if last is not None else None,
            last_run_status=last.status if last is not None else None,
            # The moment the operator means by "when did it last run": the end, or the start when it
            # is still going, or the queue when no runner has claimed it yet.
            last_run_at=(last.finished_at or last.started_at or last.queued_at) if last is not None else None,
            active_run_id=active.run_id if active is not None else None,
            active_run_status=active.status if active is not None else None,
            updated_by=channel.updated_by if channel is not None else None,
            updated_at=channel.updated_at if channel is not None else None,
        )

    @staticmethod
    def _validated_config(summary: DiffusionChannelSummary, raw: dict[str, Any]) -> dict[str, Any]:
        """The channel's own model, normalized to the JSONB shape; a bad field is a 422."""
        try:
            return summary.config_model.model_validate(raw).model_dump(exclude_none=True, mode="json")
        except ValidationError as exc:
            raise InvalidDiffusionConfigError(
                t("Configuração inválida do canal '{code}': {exc}", code=summary.code, exc=exc)
            ) from exc

    def _config_of(self, summary: DiffusionChannelSummary, channel: DiffusionChannel | None) -> dict[str, Any]:
        """The effective configuration: the model's defaults plus what the row saved."""
        if channel is None:
            return {}
        return self._validated_config(summary, dict(channel.config or {}))

    @staticmethod
    def _schedule_of(channel: DiffusionChannel | None) -> DiffusionScheduleDTO | None:
        if channel is None or not channel.cron:
            return None
        return DiffusionScheduleDTO(
            cron=channel.cron,
            timezone=channel.timezone,
            next_run_at=channel.next_run_at,
            last_enqueued_at=channel.last_enqueued_at,
            last_skipped_at=channel.last_skipped_at,
            updated_by=channel.updated_by,
            updated_at=channel.updated_at,
        )
