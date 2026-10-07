"""
Brazilian Portuguese, as the language profile.

Every literal here was read from the real collection (the measurements are in the module
that used to hold it, now the docstrings of the rules that consume it). Nothing in this
file decides anything: it states what the language *is*, and the rules in ``staging`` and
``archive`` read it.

The FTS dictionary and the spaCy model are part of the profile because they are properties
of the language too: ``search_vector`` is built with ``to_tsvector('portuguese', …)`` and the
NER presets load ``pt_core_news_lg``. Keeping them here means a second language declares
them in one place instead of hiding them in a model definition and a registry.
"""

import re

from scrinalia.core.language.base import LanguageProfile
from scrinalia.core.language.pt_br_stopwords import PT_BR_STOPWORDS

#: ``Década de 1980``, ``Anos 90``, ``Anos 1990``, ``final da década de 80``.
_DECADE_RE = re.compile(r"(?:d[ée]cada|anos)\s+(?:de\s+)?(\d{2,4})\b", re.IGNORECASE)

#: ``1951-1953``, ``1920 a 2006``, ``1929-1986``.
_RANGE_RE = re.compile(r"\b(\d{4})\s*(?:-|\u2013|\u2014|a|at\u00e9|ate)\s*(\d{4})\b", re.IGNORECASE)

#: The Brazilian ``dd/mm/yyyy`` spelling; ``local_date_order`` says the groups are day-month-year.
_BR_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")

#: A placeholder the origin wrote where no value existed (``local não identificado``).
_PLACEHOLDER_RE = re.compile(
    r"^(não identificad[oa]|local não identificad[oa]|localização não identificad[oa]|"
    r"sem identificação|ilegível|não possui|não informado)$",
    re.IGNORECASE,
)

#: Street and address prefixes. These are **places**, not non-subjects: a street with a number
#: goes to the PLACE facet rather than being discarded, while never being classified.
_STREET_RE = re.compile(
    r"^(rua|r\.|avenida|av\.|alameda|travessa|tv\.|rodovia|estrada|largo|praça|pça\.?|"
    r"br[-\s]?\d+|km\s*\d+)",
    re.IGNORECASE,
)

#: A bare number, optionally followed by a unit (``303 anos``).
_MEASURE_RE = re.compile(r"^\d+(\s*(anos?|meses?|metros?|m|km|nº\.?\s*\d*))?$", re.IGNORECASE)

#: Portuguese plural endings mapped to the singular they may come from. Applied only as
#: *candidates*: a candidate becomes a merge suggestion when the singular already exists.
_PLURAL_RULES: tuple[tuple[str, str], ...] = (
    ("ões", "ão"),
    ("ães", "ão"),
    ("ais", "al"),
    ("éis", "el"),
    ("eis", "el"),
    ("óis", "ol"),
    ("ois", "ol"),
    ("is", "il"),
    ("ns", "m"),
    ("es", "e"),
    ("s", ""),
)

PT_BR = LanguageProfile(
    code="pt-BR",
    name="Português (Brasil)",
    stopwords=frozenset(PT_BR_STOPWORDS),
    empty_date_values=frozenset(
        {
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
    ),
    decade_pattern=_DECADE_RE,
    range_pattern=_RANGE_RE,
    local_date_pattern=_BR_DATE_RE,
    local_date_order="DMY",
    min_year=1800,
    max_year=2100,
    two_digit_year_base=1900,
    placeholder_pattern=_PLACEHOLDER_RE,
    street_pattern=_STREET_RE,
    measure_pattern=_MEASURE_RE,
    plural_rules=_PLURAL_RULES,
    fts_dictionary="portuguese",
    ner_model="pt_core_news_lg",
)
