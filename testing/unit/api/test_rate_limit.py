"""The sliding window every brake shares.

A unit test because the limiter is pure state plus a clock — no database, no HTTP. The clock is
injected, so the window is exercised by moving time instead of sleeping through it, and the two
details that make a brake trustworthy are pinned here: the hit that trips the ceiling is the one
refused, and a client that waits is served again without an administrator's help.
"""

from __future__ import annotations

import pytest

from scrinalia.api.rate_limit import SlidingWindowLimiter


class FakeClock:
    """A monotonic clock a test can move by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_the_hit_that_trips_the_ceiling_is_the_one_refused(clock: FakeClock) -> None:
    """Counting before deciding, not after: otherwise every key exceeds the ceiling by one forever."""
    limiter = SlidingWindowLimiter(clock)

    assert limiter.hit("10.0.0.1", ceiling=2, window_seconds=60) is None
    assert limiter.hit("10.0.0.1", ceiling=2, window_seconds=60) is None
    assert limiter.hit("10.0.0.1", ceiling=2, window_seconds=60) == pytest.approx(60)


def test_the_refusal_says_how_long_to_wait_and_the_window_slides(clock: FakeClock) -> None:
    """A brake, not a ban: the refused caller learns the wait, and waiting is what clears it."""
    limiter = SlidingWindowLimiter(clock)
    limiter.hit("10.0.0.1", ceiling=1, window_seconds=60)

    clock.advance(15)
    assert limiter.hit("10.0.0.1", ceiling=1, window_seconds=60) == pytest.approx(45)

    clock.advance(46)
    assert limiter.hit("10.0.0.1", ceiling=1, window_seconds=60) is None


def test_a_refused_hit_does_not_extend_the_window(clock: FakeClock) -> None:
    """Hammering while refused must not push the release further away; that would be a punishment."""
    limiter = SlidingWindowLimiter(clock)
    limiter.hit("10.0.0.1", ceiling=1, window_seconds=60)

    clock.advance(30)
    assert limiter.hit("10.0.0.1", ceiling=1, window_seconds=60) == pytest.approx(30)
    clock.advance(29)
    assert limiter.hit("10.0.0.1", ceiling=1, window_seconds=60) == pytest.approx(1)
    clock.advance(2)
    assert limiter.hit("10.0.0.1", ceiling=1, window_seconds=60) is None


def test_keys_do_not_share_a_window(clock: FakeClock) -> None:
    """One noisy address must not lock out everybody behind the same installation."""
    limiter = SlidingWindowLimiter(clock)
    limiter.hit("10.0.0.1", ceiling=1, window_seconds=60)
    limiter.hit("10.0.0.1", ceiling=1, window_seconds=60)

    assert limiter.hit("10.0.0.2", ceiling=1, window_seconds=60) is None


def test_reset_forgets_every_window(clock: FakeClock) -> None:
    """The seam the test fixtures use; production has no caller."""
    limiter = SlidingWindowLimiter(clock)
    limiter.hit("10.0.0.1", ceiling=1, window_seconds=60)
    assert limiter.hit("10.0.0.1", ceiling=1, window_seconds=60) is not None

    limiter.reset()

    assert limiter.hit("10.0.0.1", ceiling=1, window_seconds=60) is None


def test_a_ceiling_or_a_window_below_one_is_still_a_brake(clock: FakeClock) -> None:
    """Configuration is not a way to remove the limit: 0 still means one hit, not infinite."""
    limiter = SlidingWindowLimiter(clock)
    assert limiter.hit("10.0.0.1", ceiling=0, window_seconds=0) is None
    assert limiter.hit("10.0.0.1", ceiling=0, window_seconds=0) == pytest.approx(1)


def test_the_mapping_drops_the_addresses_whose_window_has_passed(clock: FakeClock) -> None:
    """Memory is bounded by the addresses of the live window, not by every address ever seen."""
    limiter = SlidingWindowLimiter(clock, max_tracked=2)
    limiter.hit("10.0.0.1", ceiling=5, window_seconds=60)
    limiter.hit("10.0.0.2", ceiling=5, window_seconds=60)

    clock.advance(61)
    limiter.hit("10.0.0.3", ceiling=5, window_seconds=60)

    tracked = limiter._hits  # the bound is what this test is about
    assert set(tracked) == {"10.0.0.3"}
