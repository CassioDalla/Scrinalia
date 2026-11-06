"""A process-local sliding window, shared by the two brakes the API exposes.

One implementation for the sign-in brake and for the public surface: both answer "this address has
spent its allowance, wait a little", and two copies of the window would drift in the two details
that matter — counting the hit **before** deciding, and letting the window slide so a client that
waits is served again. The state is deliberately in the process (ADR 0025 says why), so the class
carries no database, no Redis and no HTTP.

Memory is bounded by the addresses seen inside the window, not by the addresses ever seen: the
mapping is swept when it grows past :data:`DEFAULT_MAX_TRACKED_ADDRESSES`, dropping the keys whose
hits have all expired. Without the sweep a public surface would keep one deque per address forever,
which is a slow leak with a trivial trigger.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

#: How many addresses the window may track before it drops the ones whose hits have expired. It is
#: a sweep trigger, not a hard ceiling: a burst from more distinct addresses than this inside one
#: window still tracks all of them, because forgetting a live address would hand it a fresh
#: allowance.
DEFAULT_MAX_TRACKED_ADDRESSES = 10_000


class SlidingWindowLimiter:
    """A count of hits per key over a window that slides with the clock. Thread-safe."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_tracked: int = DEFAULT_MAX_TRACKED_ADDRESSES,
    ) -> None:
        self._clock = clock
        self._max_tracked = max(1, max_tracked)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, *, ceiling: int, window_seconds: int) -> float | None:
        """
        Counts one hit from ``key``; returns ``None`` when it is allowed.

        The hit that trips the ceiling is the one refused and is **not** appended: counting after
        the decision would let every key exceed the ceiling by exactly one forever, and appending a
        refused hit would extend the window for whoever keeps knocking.

        A refusal returns the seconds until the oldest hit of the window expires, which is what a
        ``Retry-After`` needs. The caller decides whether that becomes an exception, a response or
        nothing at all.
        """
        ceiling = max(1, ceiling)
        window = max(1, window_seconds)
        now = self._clock()

        with self._lock:
            hits = self._hits[key]
            cutoff = now - window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= ceiling:
                return max(0.0, hits[0] + window - now)
            hits.append(now)
            if len(self._hits) > self._max_tracked:
                self._sweep(cutoff)
            return None

    def reset(self) -> None:
        """Forgets every window. Used by the tests, and by nothing in production."""
        with self._lock:
            self._hits.clear()

    def _sweep(self, cutoff: float) -> None:
        """Drops every key whose hits have all left the window. Called with the lock held."""
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]
