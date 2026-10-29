"""The channel service against the test database: the row, the configured flag and the refusals.

The HTTP envelope is pinned in ``testing/integration/api/controller/test_diffusion_controller.py``;
here the service is exercised directly, where a flush and a rollback are visible.
"""

import pytest
from sqlalchemy.orm import Session

from scrinalia.domains.diffusion.exceptions import (
    DiffusionChannelNotFoundError,
    InvalidDiffusionConfigError,
    PublicSiteNotConfiguredError,
)
from scrinalia.domains.diffusion.schemas import DiffusionChannelUpdateRequest, DiffusionScheduleRequest
from scrinalia.domains.diffusion.service import DiffusionChannelService


def test_the_list_starts_with_the_public_site_unconfigured(db_session: Session) -> None:
    channels = DiffusionChannelService(db_session).list_channels()

    assert [channel.code for channel in channels.channels] == ["public_site"]
    public_site = channels.channels[0]
    assert public_site.configured is False
    assert public_site.enabled is False
    assert public_site.config == {}
    assert public_site.capability == "LIVE"
    assert {field.name for field in public_site.config_fields} >= {"site_title", "locale", "allow_indexing"}


def test_the_patch_creates_the_row_and_a_pause_keeps_the_config(db_session: Session) -> None:
    service = DiffusionChannelService(db_session)

    created = service.update_channel("public_site", DiffusionChannelUpdateRequest(config={"site_title": "Acervo"}))

    assert created.configured is True
    assert created.enabled is True
    assert created.config["site_title"] == "Acervo"
    assert created.config["locale"] == "pt-BR"

    paused = service.update_channel("public_site", DiffusionChannelUpdateRequest(enabled=False))

    assert paused.enabled is False
    assert paused.config["site_title"] == "Acervo"


def test_the_public_site_identity_is_404_until_the_channel_is_enabled(db_session: Session) -> None:
    service = DiffusionChannelService(db_session)

    with pytest.raises(PublicSiteNotConfiguredError):
        service.public_site()

    service.update_channel("public_site", DiffusionChannelUpdateRequest(config={"site_title": "Acervo"}))
    identity = service.public_site()

    assert identity.site_title == "Acervo"
    assert identity.locale == "pt-BR"


def test_a_paused_public_site_answers_404(db_session: Session) -> None:
    service = DiffusionChannelService(db_session)
    service.update_channel("public_site", DiffusionChannelUpdateRequest(config={"site_title": "Acervo"}))
    service.update_channel("public_site", DiffusionChannelUpdateRequest(enabled=False))

    with pytest.raises(PublicSiteNotConfiguredError):
        service.public_site()


def test_an_empty_patch_is_refused(db_session: Session) -> None:
    service = DiffusionChannelService(db_session)

    with pytest.raises(InvalidDiffusionConfigError):
        service.update_channel("public_site", DiffusionChannelUpdateRequest())


def test_a_new_channel_needs_its_configuration_first(db_session: Session) -> None:
    service = DiffusionChannelService(db_session)

    with pytest.raises(InvalidDiffusionConfigError):
        service.update_channel("public_site", DiffusionChannelUpdateRequest(enabled=True))


def test_an_invalid_config_is_a_422_refusal(db_session: Session) -> None:
    service = DiffusionChannelService(db_session)

    with pytest.raises(InvalidDiffusionConfigError):
        service.update_channel(
            "public_site",
            DiffusionChannelUpdateRequest(config={"site_title": "Acervo", "contact_email": "nao-e-um-email"}),
        )


def test_a_live_channel_has_no_options_and_no_schedule(db_session: Session) -> None:
    service = DiffusionChannelService(db_session)

    with pytest.raises(InvalidDiffusionConfigError):
        service.update_channel(
            "public_site",
            DiffusionChannelUpdateRequest(config={"site_title": "Acervo"}, options={"formats": ["json"]}),
        )

    with pytest.raises(InvalidDiffusionConfigError):
        service.set_schedule("public_site", DiffusionScheduleRequest(cron="0 2 * * *"))

    with pytest.raises(InvalidDiffusionConfigError):
        service.clear_schedule("public_site")


def test_an_unknown_channel_is_404_and_an_unknown_code_is_named(db_session: Session) -> None:
    service = DiffusionChannelService(db_session)

    with pytest.raises(DiffusionChannelNotFoundError, match="public_site"):
        service.get_channel("nope")
