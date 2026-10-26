"""The retry policy: three attempts with bounded exponential backoff (ADR 0014/0015).

The policy is a pure function of the attempt so the rule is testable without a database and the
scheduler cannot grow a second version of it. A retry is only ever created for a **scheduled** run
that ended ``FAILED`` or ``INTERRUPTED``; the trigger check lives in the query, and this module only
answers "how long after attempt n?".
"""

from __future__ import annotations

import random

#: The total number of attempts, the first one included. The third failure is final.
MAX_ATTEMPTS = 3

#: The first backoff, doubled per attempt: 60 s, 120 s, 240 s, ...
BASE_SECONDS = 60

#: The ceiling, applied after the jitter so it is a real ceiling.
CAP_SECONDS = 30 * 60

#: The backoff is "±20%" of the base; the jitter spreads bursts of retries (several workers failing
#: on the same database restart) instead of retrying them in lockstep.
JITTER = 0.2


def retry_delay_seconds(attempt: int, *, rng: random.Random | None = None) -> int:
    """
    The delay before the retry that follows the failed ``attempt``, in whole seconds.

    ``60 x 2^(attempt-1)`` with a ±20% jitter, capped at 30 minutes **after** the jitter. ``attempt``
    is the attempt that just failed: the first failure waits about a minute, the second about two.
    """
    if attempt < 1:
        raise ValueError("attempt starts at 1")
    base = min(BASE_SECONDS * 2 ** (attempt - 1), CAP_SECONDS)
    factor = 1.0 + (rng or random).uniform(-JITTER, JITTER)
    return min(round(base * factor), CAP_SECONDS)
