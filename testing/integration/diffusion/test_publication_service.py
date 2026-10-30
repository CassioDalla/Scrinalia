"""The publication service: the preview, the token, the apply and the undo (ADR 0023, #251).

The tests are the decisions: a branch that gains its approved descendants, a child approved after
the scope, a record kept private, a ramo revoked, a batch undone. The token is tested for what it
promises — never to authorize the write, only to refuse a set that changed between the two calls.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.core.author import Author
from scrinalia.domains.diffusion import publication_service as publication_module
from scrinalia.domains.diffusion.diffusion_registry import PUBLIC_SITE_CODE
from scrinalia.domains.diffusion.exceptions import (
    InvalidDiffusionConfigError,
    PublicationBatchAlreadyUndoneError,
    PublicationNodeNotFoundError,
    PublicationPreviewStaleError,
    PublicationRefusedError,
)
from scrinalia.domains.diffusion.models import DiffusionChannelExclusion, DiffusionChannelScope
from scrinalia.domains.diffusion.publication_schemas import (
    PublicationAction,
    PublicationMode,
    PublicationRequest,
)
from scrinalia.domains.diffusion.publication_service import DiffusionPublicationService
from testing.integration.diffusion.publication_helpers import (
    a_channel,
    a_node,
    a_scope,
    an_exclusion,
    coverage_of,
)

CURATOR = Author("Curadora de teste", None)


def _publish(**overrides: object) -> PublicationRequest:
    data: dict[str, object] = {
        "action": PublicationAction.PUBLISH,
        "channel_codes": [PUBLIC_SITE_CODE],
        "node_id": "fundo",
    }
    data.update(overrides)
    return PublicationRequest.model_validate(data)


def _branch(action: PublicationAction, node_id: str = "fundo", **overrides: object) -> PublicationRequest:
    data: dict[str, object] = {
        "action": action,
        "channel_codes": [PUBLIC_SITE_CODE],
        "node_id": node_id,
    }
    data.update(overrides)
    return PublicationRequest.model_validate(data)


def _records(action: PublicationAction, description_ids: list[str], **overrides: object) -> PublicationRequest:
    data: dict[str, object] = {
        "action": action,
        "channel_codes": [PUBLIC_SITE_CODE],
        "mode": PublicationMode.RECORDS,
        "description_ids": description_ids,
    }
    data.update(overrides)
    return PublicationRequest.model_validate(data)


def test_the_preview_counts_what_a_branch_would_publish(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "a", parent_id="fundo")
    a_node(db_session, "b", parent_id="fundo")
    a_node(db_session, "pendente", parent_id="fundo", approved=False)
    db_session.commit()
    service = DiffusionPublicationService(db_session)

    preview = service.preview(_publish())

    channel = preview.channels[0]
    assert channel.code == PUBLIC_SITE_CODE
    assert channel.eligible == 3
    assert channel.skipped.not_approved == 1
    assert [sample.description_id for sample in channel.sample] == ["a", "b", "fundo"]
    assert preview.total_eligible == 3
    assert preview.token


def test_the_preview_splits_already_covered_from_excluded(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "a", parent_id="fundo")
    a_node(db_session, "b", parent_id="fundo")
    a_scope(db_session, "a", include_descendants=False)
    an_exclusion(db_session, "b", include_descendants=False)
    db_session.commit()
    service = DiffusionPublicationService(db_session)

    channel = service.preview(_publish()).channels[0]

    assert channel.eligible == 1
    assert channel.skipped.already_covered == 1
    assert channel.skipped.excluded == 1


def test_the_apply_creates_the_branch_scope_and_its_batch(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "a", parent_id="fundo")
    a_node(db_session, "b", parent_id="fundo")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _publish(note="o fundo A vai para o site")

    preview = service.preview(request)
    batch = service.apply(request, preview.token, author=CURATOR)

    assert batch.action is PublicationAction.PUBLISH
    assert batch.applied_count == 3
    assert batch.channels == [PUBLIC_SITE_CODE]
    assert batch.requested_by == CURATOR.name
    assert batch.note == "o fundo A vai para o site"
    assert coverage_of(db_session, "fundo", "a", "b") == {
        "fundo": [PUBLIC_SITE_CODE],
        "a": [PUBLIC_SITE_CODE],
        "b": [PUBLIC_SITE_CODE],
    }
    assert len(service.batches.entries(batch.batch_id)) == 1


def test_a_branch_with_no_eligible_record_is_still_publishable(db_session: Session) -> None:
    """The scope is the decision; the child approved later enters it without a second act."""
    a_channel(db_session)
    a_node(db_session, "fundo", approved=False)
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _publish()

    preview = service.preview(request)
    assert preview.channels[0].eligible == 0
    assert preview.channels[0].actionable is True

    batch = service.apply(request, preview.token, author=CURATOR)

    assert batch.applied_count == 0
    assert coverage_of(db_session, "fundo") == {}

    scope = db_session.scalar(select(DiffusionChannelScope).where(DiffusionChannelScope.node_id == "fundo"))
    assert scope is not None
    a_node(db_session, "filho", parent_id="fundo")
    db_session.commit()

    assert coverage_of(db_session, "filho") == {"filho": [PUBLIC_SITE_CODE]}


def test_a_selection_creates_one_direct_scope_per_record(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "a")
    a_node(db_session, "b")
    a_node(db_session, "c")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _records(PublicationAction.PUBLISH, ["a", "b"])

    preview = service.preview(request)
    assert preview.channels[0].eligible == 2

    service.apply(request, preview.token, author=CURATOR)

    assert coverage_of(db_session, "a", "b") == {"a": [PUBLIC_SITE_CODE], "b": [PUBLIC_SITE_CODE]}
    assert coverage_of(db_session, "c") == {}


def test_keeping_a_branch_private_revokes_its_direct_scope_and_adds_the_exclusion(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "a", parent_id="fundo")
    a_scope(db_session, "a", include_descendants=False)
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _records(PublicationAction.EXCLUDE, ["a"])

    preview = service.preview(request)
    assert preview.channels[0].eligible == 1

    batch = service.apply(request, preview.token, author=CURATOR)

    assert batch.applied_count == 1
    assert coverage_of(db_session, "a") == {}
    inclusion = db_session.scalar(select(DiffusionChannelScope).where(DiffusionChannelScope.node_id == "a"))
    exclusion = db_session.scalar(select(DiffusionChannelExclusion).where(DiffusionChannelExclusion.node_id == "a"))
    assert inclusion is not None and inclusion.revoked_at is not None
    assert exclusion is not None and exclusion.revoked_at is None
    assert len(service.batches.entries(batch.batch_id)) == 2


def test_unexclude_brings_back_what_the_branch_still_covers(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "a", parent_id="fundo")
    a_scope(db_session, "fundo")
    an_exclusion(db_session, "a", include_descendants=False)
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    assert coverage_of(db_session, "a") == {}

    request = _branch(PublicationAction.UNEXCLUDE, "a")
    preview = service.preview(request)
    assert preview.channels[0].eligible == 1

    service.apply(request, preview.token, author=CURATOR)

    assert coverage_of(db_session, "a") == {"a": [PUBLIC_SITE_CODE]}


def test_revoking_the_branch_reports_what_dies(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "a", parent_id="fundo")
    a_node(db_session, "b", parent_id="fundo")
    a_scope(db_session, "fundo")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _branch(PublicationAction.REVOKE)

    preview = service.preview(request)
    assert preview.channels[0].eligible == 3

    service.apply(request, preview.token, author=CURATOR)

    assert coverage_of(db_session, "fundo", "a", "b") == {}


def test_the_token_refuses_a_set_that_changed(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _publish()
    preview = service.preview(request)

    a_node(db_session, "novo", parent_id="fundo")
    db_session.commit()

    with pytest.raises(PublicationPreviewStaleError):
        service.apply(request, preview.token, author=CURATOR)


def test_the_token_refuses_a_request_that_is_not_the_previewed_one(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "outro")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    preview = service.preview(_publish())

    with pytest.raises(PublicationPreviewStaleError):
        service.apply(_publish(node_id="outro"), preview.token, author=CURATOR)


def test_an_expired_preview_is_refused(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    db_session.commit()
    monkeypatch.setattr(publication_module, "PREVIEW_TTL", timedelta(seconds=-1))
    service = DiffusionPublicationService(db_session)
    request = _publish()
    preview = service.preview(request)

    with pytest.raises(PublicationPreviewStaleError):
        service.apply(request, preview.token, author=CURATOR)


def test_an_already_published_branch_has_nothing_to_confirm(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_scope(db_session, "fundo")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _publish()

    preview = service.preview(request)
    assert preview.channels[0].actionable is False
    assert preview.channels[0].eligible == 0

    with pytest.raises(PublicationRefusedError):
        service.apply(request, preview.token, author=CURATOR)


def test_the_undo_restores_the_created_scope_and_closes_the_batch(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    a_node(db_session, "a", parent_id="fundo")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _publish()
    batch = service.apply(request, service.preview(request).token, author=CURATOR)

    undone = service.undo(batch.batch_id, author=CURATOR)

    assert undone.restored == 1
    assert undone.skipped == 0
    assert coverage_of(db_session, "fundo", "a") == {}

    with pytest.raises(PublicationBatchAlreadyUndoneError):
        service.undo(batch.batch_id, author=CURATOR)


def test_the_undo_skips_a_scope_that_changed_since(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _publish()
    batch = service.apply(request, service.preview(request).token, author=CURATOR)
    scope = db_session.scalar(select(DiffusionChannelScope).where(DiffusionChannelScope.node_id == "fundo"))
    assert scope is not None
    scope.revoked_at = datetime.now(UTC)
    db_session.commit()

    undone = service.undo(batch.batch_id, author=CURATOR)

    assert undone.restored == 0
    assert undone.skipped == 1


def test_a_paused_channel_refuses_the_preview(db_session: Session) -> None:
    a_channel(db_session, enabled=False)
    a_node(db_session, "fundo")
    db_session.commit()

    with pytest.raises(InvalidDiffusionConfigError):
        DiffusionPublicationService(db_session).preview(_publish())


def test_a_missing_node_is_not_found(db_session: Session) -> None:
    a_channel(db_session)
    db_session.commit()

    with pytest.raises(PublicationNodeNotFoundError):
        DiffusionPublicationService(db_session).preview(_publish(node_id="nao-existe"))


def test_the_history_lists_the_batches_newest_first(db_session: Session) -> None:
    a_channel(db_session)
    a_node(db_session, "fundo")
    db_session.commit()
    service = DiffusionPublicationService(db_session)
    request = _publish()
    first = service.apply(request, service.preview(request).token, author=CURATOR)
    second_request = _branch(PublicationAction.REVOKE)
    second = service.apply(second_request, service.preview(second_request).token, author=CURATOR)

    history = service.history()

    assert [batch.batch_id for batch in history.batches] == [second.batch_id, first.batch_id]
    assert history.batches[0].action is PublicationAction.REVOKE
    assert history.batches[0].channels == [PUBLIC_SITE_CODE]
