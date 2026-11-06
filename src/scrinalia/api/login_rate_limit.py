"""A per-address brake on sign-in attempts, in front of the per-account lockout.

The lockout protects one account; this protects the *endpoint*. Without it, one address can walk the
whole account list at full speed — each address gets its own few free guesses, and the per-account
counter never fires because no single account is hit often enough.

It is deliberately a **process-local** sliding window, and that is a documented limitation rather than
an oversight: the durable guarantee is the account lockout, which is a column and survives a restart,
while this is a brake that resets with the process. A shared store (Redis) would be a new piece of
infrastructure for a system that is meant to be installed offline by one institution, and the API is
single-process by design (ADR 0004). The day that changes, this moves with the executor.

The window itself is ``api/rate_limit.py``'s, shared with the public surface's brake: the two differ
in what they count and in what a refusal becomes, never in how the window slides.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from scrinalia.api.rate_limit import SlidingWindowLimiter
from scrinalia.core.config import get_settings
from scrinalia.core.i18n import refusal
from scrinalia.domains.identity.exceptions import TooManyLoginAttemptsError


class LoginRateLimiter:
    """A sliding window of sign-in attempts per client address. Thread-safe."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._window = SlidingWindowLimiter(clock)

    def check(self, address: str) -> None:
        """
        Counts one attempt from ``address`` and refuses when the window is already full.

        Counting **before** deciding means the attempt that trips the ceiling is the one refused:
        counting after would let every address exceed the ceiling by exactly one, forever. The window
        slides, so a client that waits is served again without an administrator's help.
        """
        settings = get_settings()
        retry_after = self._window.hit(
            address,
            ceiling=settings.AUTH_LOGIN_RATE_MAX,
            window_seconds=settings.AUTH_LOGIN_RATE_WINDOW_SECONDS,
        )
        if retry_after is not None:
            raise TooManyLoginAttemptsError(refusal("auth.too_many_attempts"))

    def reset(self) -> None:
        """Forgets every window. Used by the tests, and by nothing in production."""
        self._window.reset()
