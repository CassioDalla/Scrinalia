"""The retry policy: three attempts and a bounded exponential backoff (ADR 0015)."""

from random import Random

import pytest

from scrinalia.domains.archive.workers.retry import CAP_SECONDS, MAX_ATTEMPTS, retry_delay_seconds


def test_the_policy_is_three_attempts() -> None:
    assert MAX_ATTEMPTS == 3


def test_the_first_retry_waits_about_a_minute() -> None:
    # 60 s ±20%.
    assert 48 <= retry_delay_seconds(1, rng=Random(7)) <= 72


def test_the_delay_doubles_per_attempt() -> None:
    assert 96 <= retry_delay_seconds(2, rng=Random(7)) <= 144
    assert 192 <= retry_delay_seconds(3, rng=Random(7)) <= 288


def test_the_cap_is_the_ceiling_after_the_jitter() -> None:
    assert retry_delay_seconds(20, rng=Random(7)) <= CAP_SECONDS


def test_attempt_zero_is_refused() -> None:
    with pytest.raises(ValueError):
        retry_delay_seconds(0)
