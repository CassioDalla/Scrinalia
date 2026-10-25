"""The cron expression and the next occurrence of a schedule (ADR 0015).

The expression is the five-field cron (``minute hour day-of-month month day-of-week``) evaluated in
an explicit IANA zone; the occurrence is returned in UTC because that is how the database stores a
``timestamptz`` and how the scheduler compares it with ``now()``. The conversion must happen in the
zone: evaluating "02:00" in UTC would run at 23:00 in São Paulo and, worse, would ignore the DST
transition entirely.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from croniter.croniter import CroniterBadCronError, CroniterError


class InvalidCronError(ValueError):
    """The expression is not a five-field cron the scheduler can evaluate."""


class InvalidTimezoneError(ValueError):
    """The zone is not an IANA name the standard library knows."""


def validate_cron(expression: str) -> str:
    """
    The expression, stripped, or ``InvalidCronError`` with the field count and the shape.

    Five fields is a deliberate restriction: the seconds field and the ``@daily`` aliases are the two
    places a cron expression stops being the thing an operator reads off an example. The message is
    English here (an internal error); the service turns it into the panel's sentence.
    """
    expression = expression.strip()
    if len(expression.split()) != 5:
        raise InvalidCronError("the schedule needs five fields: minute hour day-of-month month day-of-week")
    try:
        croniter(expression)
    except (CroniterBadCronError, CroniterError, ValueError) as exc:
        raise InvalidCronError(f"'{expression}' is not a valid cron expression") from exc
    return expression


def validate_timezone(name: str) -> str:
    """The IANA name, or ``InvalidTimezoneError``."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezoneError(f"'{name}' is not a known IANA timezone") from exc
    return name


def next_occurrence(
    expression: str,
    timezone: str,
    after: datetime,
    *,
    previous: datetime | None = None,
) -> datetime:
    """
    The first occurrence strictly after ``after``, computed in ``timezone`` and returned in UTC.

    ``after`` must be timezone-aware (the scheduler passes the database's ``now()``). The DST rules
    are the zone's: the spring-forward gap has no wall time to run at, and the croniter resolves it to
    the next valid instant (03:00, not a nonexistent 02:00).

    ``previous`` is the occurrence that just fired. On the fall-back day the same wall time exists
    twice, and croniter returns both; passing the previous one makes the walk skip the second, so a
    "daily at 01:30" runs once on that day, which is what the schedule promises.
    """
    zone = ZoneInfo(timezone)
    base = after.astimezone(zone)
    iterator = croniter(expression, base)
    candidate = iterator.get_next(datetime)
    if previous is not None:
        previous_wall = previous.astimezone(zone).replace(tzinfo=None)
        while candidate.astimezone(zone).replace(tzinfo=None) == previous_wall:
            candidate = iterator.get_next(datetime)
    return candidate.astimezone(UTC)
