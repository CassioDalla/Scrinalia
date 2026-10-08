"""Unit tests of the staging date parser (pure, no database)."""

from datetime import date

import pytest

from scrinalia.domains.staging.dates import parse_document_date


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Placeholders from the source: the measured 1682 "00/00/0000" case.
        ("00/00/0000", None),
        ("0000-00-00", None),
        ("s/ data definida", None),
        ("Sem data", None),
        ("data indefinida", None),
        ("?", None),
        ("-", None),
        ("", None),
        ("   ", None),
        (None, None),
        # Complete dates.
        ("15/03/1954", date(1954, 3, 15)),
        ("1972-05-10", date(1972, 5, 10)),
        ("1929-07-05T03:00:00Z", date(1929, 7, 5)),
        ("Data: 05/07/1929", date(1929, 7, 5)),
        # Decades, in every spelling the collection uses.
        ("Década de 1980", date(1980, 1, 1)),
        ("decada de 80", date(1980, 1, 1)),
        ("Anos 90", date(1990, 1, 1)),
        ("Anos 1990", date(1990, 1, 1)),
        ("Final da década de 1980", date(1980, 1, 1)),
        ("Começo da década de 1970", date(1970, 1, 1)),
        # Approximations keep the year they name.
        ("Após 1996", date(1996, 1, 1)),
        ("A partir de 1972", date(1972, 1, 1)),
        ("Meados de 1970", date(1970, 1, 1)),
        ("Meados de 1993", date(1993, 1, 1)),
        # Ranges become their start.
        ("1951-1953", date(1951, 1, 1)),
        ("1920 a 2006", date(1920, 1, 1)),
        ("1929\u20131986", date(1929, 1, 1)),
        # Bare year.
        ("1980", date(1980, 1, 1)),
        # A broken day/month keeps the year instead of losing the document.
        ("03/00/1954", date(1954, 1, 1)),
        # Out of the plausible window: a code, not a date.
        ("9999", None),
        ("1234", None),
    ],
)
def test_parse_document_date(raw, expected) -> None:
    assert parse_document_date(raw) == expected


def test_two_digit_years_look_backwards() -> None:
    """A photographic archive: "anos 20" is 1920, never 2020."""
    assert parse_document_date("Anos 20") == date(1920, 1, 1)
    assert parse_document_date("Década de 70") == date(1970, 1, 1)


def test_a_placeholder_is_not_a_year_zero() -> None:
    """Regression: ``00/00/0000`` used to explode inside ``date(0, 0, 0)`` and be swallowed."""
    assert parse_document_date("00/00/0000") is None


def test_a_range_is_not_read_as_an_iso_date() -> None:
    assert parse_document_date("1972-1992") == date(1972, 1, 1)
