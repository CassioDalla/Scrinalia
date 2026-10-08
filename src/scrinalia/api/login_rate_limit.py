"""A per-address brake on sign-in attempts, in front of the per-account lockout.

The lockout protects one account; this protects the *endpoint*. Without it, one address can walk the
whole account list at full speed — each address gets its own few free guesses, and the per-account
counter never fires because no single account is hit often enough.

It is deliberately a **process-local** sliding window, and that is a documented limitation rather than
an oversight: the durable guarantee is the account lockout, which is a column and survives a restart,
while this is a brake that resets with the process. A shared store (Redis) would be a new piece of
infrastructure for a system that is meant to be installed offline by one institution, and the API is
single-process by design (ADR 0004). The day that changes, this moves with the executor.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from scrinalia.core.config import get_settings
from scrinalia.domains.identity.exceptions import TooManyLoginAttemptsError

TOO_MANY_ATTEMPTS_MESSAGE = "Muitas tentativas de acesso a partir deste endereço. Aguarde alguns minutos."


class LoginRateLimiter:
    """A sliding window of sign-in attempts per client address. Thread-safe."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, address: str) -> None:
        """
        Counts one attempt from ``address`` and refuses when the window is already full.

        Counting **before** deciding means the attempt that trips the ceiling is the one refused:
        counting after would let every address exceed the ceiling by exactly one, forever. The window
        slides, so a client that waits is served again without an administrator's help.
        """
        settings = get_settings()
        window = max(1, settings.AUTH_LOGIN_RATE_WINDOW_SECONDS)
        ceiling = max(1, settings.AUTH_LOGIN_RATE_MAX)
        now = self._clock()

        with self._lock:
            hits = self._hits[address]
            cutoff = now - window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= ceiling:
                raise TooManyLoginAttemptsError(TOO_MANY_ATTEMPTS_MESSAGE)
            hits.append(now)

    def reset(self) -> None:
        """Forgets every window. Used by the tests, and by nothing in production."""
        with self._lock:
            self._hits.clear()
