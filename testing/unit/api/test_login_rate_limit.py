"""The per-address sign-in brake: a sliding window that refuses the attempt that trips it.

A unit test because the limiter is pure state plus a clock — no database, no HTTP. The clock is
injected, so the window is exercised by moving time instead of sleeping through it.
"""

import pytest

from scrinalia.api.login_rate_limit import LoginRateLimiter
from scrinalia.core.config import settings
from scrinalia.domains.identity.exceptions import TooManyLoginAttemptsError


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


@pytest.fixture(autouse=True)
def tight_window(monkeypatch) -> None:
    """Two attempts per minute: the smallest window that still has a "second" attempt to count."""
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_MAX", 2)
    monkeypatch.setattr(settings, "AUTH_LOGIN_RATE_WINDOW_SECONDS", 60)


def test_the_attempt_that_trips_the_ceiling_is_the_one_refused(clock: FakeClock) -> None:
    """
    Counting before deciding, not after: otherwise every address exceeds the ceiling by one forever.
    """
    limiter = LoginRateLimiter(clock=clock)

    limiter.check("10.0.0.1")
    limiter.check("10.0.0.1")

    with pytest.raises(TooManyLoginAttemptsError):
        limiter.check("10.0.0.1")


def test_the_window_slides_so_a_client_that_waits_is_served_again(clock: FakeClock) -> None:
    """A brake, not a ban: nobody has to be unlocked by an administrator."""
    limiter = LoginRateLimiter(clock=clock)
    limiter.check("10.0.0.1")
    limiter.check("10.0.0.1")
    with pytest.raises(TooManyLoginAttemptsError):
        limiter.check("10.0.0.1")

    clock.advance(61)

    limiter.check("10.0.0.1")


def test_addresses_do_not_share_a_window(clock: FakeClock) -> None:
    """One noisy address must not lock out everybody behind the same installation."""
    limiter = LoginRateLimiter(clock=clock)
    limiter.check("10.0.0.1")
    limiter.check("10.0.0.1")

    limiter.check("10.0.0.2")


def test_reset_forgets_every_window(clock: FakeClock) -> None:
    """The seam the test fixtures use; production has no caller."""
    limiter = LoginRateLimiter(clock=clock)
    limiter.check("10.0.0.1")
    limiter.check("10.0.0.1")
    with pytest.raises(TooManyLoginAttemptsError):
        limiter.check("10.0.0.1")

    limiter.reset()

    limiter.check("10.0.0.1")
