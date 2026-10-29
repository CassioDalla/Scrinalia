"""The run ledger's two axes: the origin of ``ingestion`` and the channel of ``diffusion``.

ADR 0016 gave the ledger one axis so one ``ingestion`` worker could serve several origins without
sharing a slot; ADR 0023 §7 does the same for the diffusion export, whose run names the channel it
writes. These tests pin the three cases the partial unique index cannot tell apart on its own — a
run with the wrong axis, or with both — and the slot the index really enforces: two channels export
at the same time, a second run of one channel waits, and an origin never shares a slot with a
channel.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models.enums import WorkerRunTrigger
from scrinalia.domains.archive.repository.worker_run_repo import WorkerRunRepository


def _queued(
    repo: WorkerRunRepository,
    worker_name: str,
    *,
    origin: str | None = None,
    channel: str | None = None,
):
    """Accepts one queued run with the axis the worker has, and nothing else."""
    return repo.create_queued(
        worker_name,
        trigger=WorkerRunTrigger.API,
        requested_by=None,
        engine_name=None,
        preset=None,
        config={},
        origin_code=origin,
        channel_code=channel,
    )


def test_two_channels_export_at_the_same_time(db_session: Session) -> None:
    repo = WorkerRunRepository(db_session)

    first = _queued(repo, "diffusion", channel="channel_a")
    second = _queued(repo, "diffusion", channel="channel_b")

    assert (first.channel_code, second.channel_code) == ("channel_a", "channel_b")
    assert first.origin_code is None and second.origin_code is None
    assert repo.has_active_run("diffusion", channel_code="channel_a") is True
    assert repo.has_active_run("diffusion", channel_code="channel_b") is True


def test_a_second_run_of_one_channel_is_refused(db_session: Session) -> None:
    repo = WorkerRunRepository(db_session)
    _queued(repo, "diffusion", channel="channel_a")

    with pytest.raises(IntegrityError):
        _queued(repo, "diffusion", channel="channel_a")


def test_an_origin_and_a_channel_never_share_a_slot(db_session: Session) -> None:
    repo = WorkerRunRepository(db_session)

    origin = _queued(repo, "ingestion", origin="pmc")
    channel = _queued(repo, "diffusion", channel="channel_a")
    archive = _queued(repo, "ner")

    assert (origin.origin_code, origin.channel_code) == ("pmc", None)
    assert (channel.channel_code, channel.origin_code) == ("channel_a", None)
    assert (archive.origin_code, archive.channel_code) == (None, None)
    # Each one holds its own slot: the three rows coexist, and each lookup finds only its own.
    assert repo.has_active_run("ingestion", origin_code="pmc") is True
    assert repo.has_active_run("diffusion", channel_code="channel_a") is True
    assert repo.has_active_run("ner") is True
    assert repo.has_active_run("diffusion", channel_code="pmc") is False


def test_the_writer_refuses_the_wrong_axis(db_session: Session) -> None:
    """The catalogue is the one definition; the writer applies it to every insert."""
    repo = WorkerRunRepository(db_session)

    with pytest.raises(ValueError, match="channel"):
        _queued(repo, "diffusion", origin="pmc")
    with pytest.raises(ValueError, match="origin"):
        _queued(repo, "ingestion", channel="channel_a")
    with pytest.raises(ValueError, match="neither"):
        _queued(repo, "ner", channel="channel_a")
    with pytest.raises(ValueError, match="channel"):
        _queued(repo, "diffusion")


def test_the_claim_and_the_dto_carry_the_channel(db_session: Session) -> None:
    repo = WorkerRunRepository(db_session)
    run = _queued(repo, "diffusion", channel="channel_a")

    claimed = repo.claim_next(["diffusion"], runner_id="runner-a", lease_seconds=60)

    assert claimed is not None
    assert (claimed.worker_name, claimed.channel_code, claimed.origin_code) == ("diffusion", "channel_a", None)
    stored = repo.get(run.run_id)
    assert stored is not None
    assert stored.channel_code == "channel_a"
