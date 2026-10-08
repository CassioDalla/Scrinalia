"""
Date parsing for the Staging layer (Fase 3.5-D).

Measured on the real collection: of the 1925 documents with no parsed date, **1682 carry
the literal ``"00/00/0000"``** — a source placeholder for "no date", not a lost value. The
remaining ones are real expressions the old parser never understood ("Década de 1980",
"1951-1953", "Após 1996", "Meados de 1970").

The **grammar** of those expressions is Portuguese and lives in the language profile
(:mod:`scrinalia.core.language.pt_br`): the placeholders, the decade and range expressions
and the ``dd/mm/yyyy`` spelling are properties of the language. What stays here is the
*order* of the attempts, which is the algorithm and is the same in every language.

Two decisions are deliberate:

* A placeholder is turned into ``None`` on purpose. ``\"00/00/0000\"`` used to reach
  ``date(0, 0, 0)``, raise ``ValueError`` and be swallowed by a bare ``except``: the value
  was already absent, but nothing said so.
* An approximate expression becomes a real ``date`` at the precision the source has
  (decade and year become January 1st, a range becomes its start), consistent with what
  the layer already did for a bare year. Being explicit about the imprecision would need
  new columns, and that decision belongs to the phase that owns the date facet.
"""

import re
from datetime import date

from scrinalia.core.language import get_language

#: Any isolated four-digit year: ``Após 1996``, ``Meados de 1970``, ``A partir de 1972``.
_YEAR_RE = re.compile(r"\b(\d{4})\b")

#: The ISO spelling is not a language choice: it is the interchange format.
_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _two_digit_year(value: str, base: int) -> int:
    """``90`` means 1990: the collection is historical, so two digits always look back."""
    return base + int(value)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _year_from(value: str, *, base: int, min_year: int, max_year: int) -> int | None:
    year = _two_digit_year(value, base) if len(value) == 2 else int(value)
    return year if min_year <= year <= max_year else None


def _ordered(groups: tuple[str, ...], order: str) -> tuple[int, int, int]:
    """Reads ``(year, month, day)`` out of the local pattern's groups, per the profile's order."""
    parsed = dict(zip(order, (int(part) for part in groups), strict=True))
    return parsed["Y"], parsed["M"], parsed["D"]


def parse_document_date(raw: object | None) -> date | None:
    """
    Turns the source spelling into a date, or ``None`` when there is no usable date.

    Order matters: placeholders first (``00/00/0000`` would otherwise be a syntax error),
    then a complete date, then the fuzzy expressions, then a range, and finally any
    isolated year. An unparseable full date still falls through to the year, which is how
    ``"03/00/1954"`` keeps its 1954 instead of becoming ``None``.
    """
    if raw is None:
        return None

    language = get_language()
    text = str(raw).strip()
    if text.lower() in language.empty_date_values:
        return None

    local = language.local_date_pattern.search(text)
    if local:
        parsed = _safe_date(*_ordered(local.groups(), language.local_date_order))
        if parsed:
            return parsed

    iso = _ISO_RE.search(text)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
        parsed = _safe_date(year, month, day)
        if parsed:
            return parsed

    bounds = {"base": language.two_digit_year_base, "min_year": language.min_year, "max_year": language.max_year}

    decade = language.decade_pattern.search(text)
    if decade:
        year = _year_from(decade.group(1), **bounds)
        if year:
            return date(year, 1, 1)

    ranged = language.range_pattern.search(text)
    if ranged:
        year = _year_from(ranged.group(1), **bounds)
        if year:
            return date(year, 1, 1)

    single = _YEAR_RE.search(text)
    if single:
        year = _year_from(single.group(1), **bounds)
        if year:
            return date(year, 1, 1)

    return None
