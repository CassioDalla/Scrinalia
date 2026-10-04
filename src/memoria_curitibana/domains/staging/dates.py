"""
Date parsing for the Staging layer (Fase 3.5-D).

Measured on the real collection: of the 1925 documents with no parsed date, **1682 carry
the literal ``"00/00/0000"``** — a source placeholder for "no date", not a lost value. The
remaining ones are real expressions the old parser never understood ("Década de 1980",
"1951-1953", "Após 1996", "Meados de 1970").

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

#: Values the source uses to say "there is no date". Kept explicit and lowercase.
EMPTY_DATE_VALUES = {
    "",
    "-",
    "?",
    "n/a",
    "na",
    "não informado",
    "nao informado",
    "sem data",
    "s/ data definida",
    "s/data",
    "s/ data",
    "data indefinida",
    "00/00/0000",
    "0000-00-00",
    "00000000",
}

#: ``Década de 1980``, ``Anos 90``, ``Anos 1990``, ``final da década de 80``.
_DECADE_RE = re.compile(r"(?:d[ée]cada|anos)\s+(?:de\s+)?(\d{2,4})\b", re.IGNORECASE)

#: ``1951-1953``, ``1920 a 2006``, ``1929-1986``.
_RANGE_RE = re.compile(r"\b(\d{4})\s*(?:-|\u2013|\u2014|a|at\u00e9|ate)\s*(\d{4})\b", re.IGNORECASE)

#: Any isolated four-digit year: ``Após 1996``, ``Meados de 1970``, ``A partir de 1972``.
_YEAR_RE = re.compile(r"\b(\d{4})\b")

_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_BR_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")

#: A year outside this window is a code, not a date (the collection starts in 1850).
MIN_YEAR = 1800
MAX_YEAR = 2100


def _two_digit_year(value: str) -> int:
    """``90`` means 1990: the collection is historical, so two digits always look back."""
    return 1900 + int(value)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _year_from(value: str) -> int | None:
    year = _two_digit_year(value) if len(value) == 2 else int(value)
    return year if MIN_YEAR <= year <= MAX_YEAR else None


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

    text = str(raw).strip()
    if text.lower() in EMPTY_DATE_VALUES:
        return None

    brazilian = _BR_RE.search(text)
    if brazilian:
        day, month, year = (int(part) for part in brazilian.groups())
        parsed = _safe_date(year, month, day)
        if parsed:
            return parsed

    iso = _ISO_RE.search(text)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
        parsed = _safe_date(year, month, day)
        if parsed:
            return parsed

    decade = _DECADE_RE.search(text)
    if decade:
        year = _year_from(decade.group(1))
        if year:
            return date(year, 1, 1)

    ranged = _RANGE_RE.search(text)
    if ranged:
        year = _year_from(ranged.group(1))
        if year:
            return date(year, 1, 1)

    single = _YEAR_RE.search(text)
    if single:
        year = _year_from(single.group(1))
        if year:
            return date(year, 1, 1)

    return None
