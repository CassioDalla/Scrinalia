"""The cron, the zone and the next occurrence of a schedule (ADR 0015)."""

from datetime import UTC, datetime

import pytest

from scrinalia.domains.archive.workers.schedule import (
    InvalidCronError,
    InvalidTimezoneError,
    next_occurrence,
    validate_cron,
    validate_timezone,
)


def test_the_expression_is_stripped_and_kept() -> None:
    assert validate_cron(" 0 2 * * * ") == "0 2 * * *"


def test_six_fields_are_refused() -> None:
    with pytest.raises(InvalidCronError, match="five fields"):
        validate_cron("0 0 2 * * *")


def test_an_unreadable_field_is_refused() -> None:
    with pytest.raises(InvalidCronError):
        validate_cron("0 2 * * nope")


def test_the_zone_is_an_iana_name() -> None:
    assert validate_timezone("America/Sao_Paulo") == "America/Sao_Paulo"
    with pytest.raises(InvalidTimezoneError):
        validate_timezone("Mars/Olympus")


def test_the_next_occurrence_is_computed_in_the_zone_not_in_utc() -> None:
    # 02:00 in São Paulo is 05:00 UTC; computing the cron in UTC would run at 23:00 the day before.
    assert next_occurrence("0 2 * * *", "America/Sao_Paulo", datetime(2026, 10, 25, 12, 0, tzinfo=UTC)) == datetime(
        2026, 10, 26, 5, 0, tzinfo=UTC
    )


def test_an_interval_advances_to_the_next_step() -> None:
    assert next_occurrence("*/10 * * * *", "UTC", datetime(2026, 10, 25, 12, 1, tzinfo=UTC)) == datetime(
        2026, 10, 25, 12, 10, tzinfo=UTC
    )


def test_the_spring_forward_runs_at_the_next_valid_instant() -> None:
    # New York, 2026-03-08: 02:00 does not exist; 03:00 EDT is 07:00 UTC.
    assert next_occurrence("0 2 * * *", "America/New_York", datetime(2026, 3, 8, 0, 0, tzinfo=UTC)) == datetime(
        2026, 3, 8, 7, 0, tzinfo=UTC
    )


def test_the_fall_back_wall_time_runs_once() -> None:
    # The first 01:30 is EDT (05:30Z); the same wall time repeats in EST (06:30Z) and must be skipped.
    fired = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert next_occurrence("30 1 * * *", "America/New_York", fired, previous=fired) == datetime(
        2026, 11, 2, 6, 30, tzinfo=UTC
    )
