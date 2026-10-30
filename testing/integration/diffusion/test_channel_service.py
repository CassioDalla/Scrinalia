"""The channel service against the test database: the row, the configured flag and the refusals.

The HTTP envelope is pinned in ``testing/integration/api/controller/test_diffusion_controller.py``;
here the service is exercised directly, where a flush and a rollback are visible.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import WorkerRunAlreadyActiveError
from scrinalia.domains.archive.models.operations import WorkerRun
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger
from scrinalia.domains.diffusion.diffusion_registry import CHANNELS
from scrinalia.domains.diffusion.exceptions import (
    DiffusionAdapterMissingError,
    DiffusionChannelNotFoundError,
    InvalidDiffusionConfigError,
    PublicSiteNotConfiguredError,
)
from scrinalia.domains.diffusion.schemas import DiffusionChannelUpdateRequest, DiffusionScheduleRequest
from scrinalia.domains.diffusion.service import DiffusionChannelService
from testing.integration.diffusion.fake_channel import FAKE_EXPORT, FAKE_WITHOUT_ADAPTER


def test_the_list_starts_with_the_public_site_unconfigured(db_session: Session) -> None:
    channels = DiffusionChannelService(db_session).list_channels()

    assert [channel.code for channel in channels.channels] == ["public_site", "dataset"]
    public_site = channels.channels[0]
    assert public_site.configured is False
    assert public_site.enabled is False
    assert public_site.config == {}
    assert public_site.capability == "LIVE"
    assert {field.name for field in public_site.config_fields} >= {"site_title", "locale", "allow_indexing"}

    dataset = channels.channels[1]
    assert dataset.configured is False
    assert dataset.capability == "EXPORT"
    assert {field.name for field in dataset.config_fields} >= {"dataset_title", "destination_path", "license_id"}


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


# --- the manual export run ---------------------------------------------------------------------


@contextmanager
def _shared(db: Session) -> Iterator[Session]:
    """Hands the test's session to the ledger without closing it on the way out."""
    yield db


def _service(db: Session) -> DiffusionChannelService:
    return DiffusionChannelService(db, ledger=WorkerRunLedger(session_factory=lambda: _shared(db)))


def _configured(db: Session, code: str = "fake_export", *, enabled: bool = True) -> DiffusionChannelService:
    service = _service(db)
    service.update_channel(code, DiffusionChannelUpdateRequest(config={}, enabled=enabled))
    return service


def test_the_manual_run_enqueues_a_diffusion_row(db_session: Session, monkeypatch) -> None:
    monkeypatch.setitem(CHANNELS, "fake_export", FAKE_EXPORT)
    service = _configured(db_session)

    run = service.trigger("fake_export", requested_by=Author("test"))

    assert run.worker_name == "diffusion"
    assert run.channel_code == "fake_export"
    assert run.origin_code is None
    assert run.status.value == "QUEUED"
    stored = db_session.get(WorkerRun, run.run_id)
    assert stored is not None and stored.request == {"options": {}}
    assert WorkerRunRepository(db_session).has_active_run("diffusion", channel_code="fake_export") is True


def test_a_second_run_of_the_same_channel_is_refused(db_session: Session, monkeypatch) -> None:
    monkeypatch.setitem(CHANNELS, "fake_export", FAKE_EXPORT)
    service = _configured(db_session)
    service.trigger("fake_export")

    with pytest.raises(WorkerRunAlreadyActiveError):
        service.trigger("fake_export")


def test_a_live_channel_has_no_run(db_session: Session) -> None:
    service = _service(db_session)
    service.update_channel("public_site", DiffusionChannelUpdateRequest(config={"site_title": "Acervo"}))

    with pytest.raises(InvalidDiffusionConfigError, match="não tem execução"):
        service.trigger("public_site")


def test_a_paused_channel_refuses_a_run(db_session: Session, monkeypatch) -> None:
    monkeypatch.setitem(CHANNELS, "fake_export", FAKE_EXPORT)
    service = _configured(db_session, enabled=False)

    with pytest.raises(InvalidDiffusionConfigError, match="pausado"):
        service.trigger("fake_export")


def test_a_channel_without_an_adapter_is_refused(db_session: Session, monkeypatch) -> None:
    monkeypatch.setitem(CHANNELS, "fake_without_adapter", FAKE_WITHOUT_ADAPTER)
    service = _configured(db_session, "fake_without_adapter")

    with pytest.raises(DiffusionAdapterMissingError, match="não exporta"):
        service.trigger("fake_without_adapter")


def test_an_unknown_channel_is_404(db_session: Session) -> None:
    with pytest.raises(DiffusionChannelNotFoundError):
        _service(db_session).trigger("nope")


def test_the_channel_dto_carries_the_last_and_the_active_run(db_session: Session, monkeypatch) -> None:
    monkeypatch.setitem(CHANNELS, "fake_export", FAKE_EXPORT)
    service = _configured(db_session)
    run = service.trigger("fake_export")

    channel = next(item for item in service.list_channels().channels if item.code == "fake_export")

    assert channel.last_run_id == run.run_id
    assert channel.last_run_status == run.status
    assert channel.last_run_at is not None
    assert channel.active_run_id == run.run_id
    assert channel.active_run_status == run.status
