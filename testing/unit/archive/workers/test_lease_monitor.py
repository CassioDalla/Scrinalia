"""The lease monitor: the one thread that proves a runner is alive (ADR 0014)."""

import time
from collections.abc import Sequence

import pytest

from scrinalia.domains.archive.workers.lease import RunLeaseMonitor


class FakeLedger:
    """Records the beats; the real ledger writes them through its own committed session."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, list[int] | None]] = []

    def heartbeat(self, runner_id: str, *, lease_seconds: int, run_ids: Sequence[int] | None = None) -> int:
        self.calls.append((runner_id, lease_seconds, list(run_ids) if run_ids is not None else None))
        return 1


def _monitor(ledger: FakeLedger, *, interval: int = 15) -> RunLeaseMonitor:
    return RunLeaseMonitor(
        "runner-a", lease_seconds=60, interval_seconds=interval, ledger=ledger, heartbeat_runner=False
    )


def test_a_beat_renews_the_runs_it_tracks() -> None:
    ledger = FakeLedger()
    monitor = _monitor(ledger)
    monitor.track(7)

    monitor.beat_now()

    assert ledger.calls == [("runner-a", 60, [7])]


def test_an_empty_tracked_set_renews_every_running_row_the_runner_owns() -> None:
    ledger = FakeLedger()
    monitor = _monitor(ledger)
    monitor.track(7)
    monitor.release(7)

    monitor.beat_now()

    assert ledger.calls == [("runner-a", 60, None)]


def test_releasing_a_run_stops_its_renewal() -> None:
    ledger = FakeLedger()
    monitor = _monitor(ledger)
    monitor.track(7)
    monitor.track(8)
    monitor.release(7)

    monitor.beat_now()

    assert ledger.calls[-1] == ("runner-a", 60, [8])


def test_the_heartbeat_must_fit_inside_the_lease() -> None:
    with pytest.raises(ValueError, match="smaller"):
        _monitor(FakeLedger(), interval=60)


def test_the_thread_beats_until_it_is_stopped() -> None:
    ledger = FakeLedger()
    monitor = _monitor(ledger, interval=1)

    monitor.start()
    time.sleep(1.2)
    monitor.stop()

    assert ledger.calls
