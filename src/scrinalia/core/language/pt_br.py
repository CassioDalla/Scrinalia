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

#: The spellings the origin used where a *text* field carried no information.
#:
#: This is the one definition of "the origin wrote nothing". Before it existed the fact was declared
#: four times — in the date parser, in the subject guard's regex, in the staging text cleaner and in
#: the title validator — and ``não informado`` alone lived in three of them. A fifth spelling added
#: in one place was silently not a false null in the others.
_FALSE_NULL_VALUES: frozenset[str] = frozenset(
    {
        "",
        "-",
        "?",
        "n/a",
        "na",
        "não informado",
        "nao informado",
        "nenhum",
        "sem título",
        "sem titulo",
        "não identificado",
        "não identificada",
        "local não identificado",
        "local não identificada",
        "localização não identificado",
        "localização não identificada",
        "sem identificação",
        "ilegível",
        "não possui",
        "sem data",
        "s/ data definida",
        "s/data",
        "s/ data",
        "data indefinida",
    }
)

#: The date-shaped placeholders. They extend the set for the **date parser only**: the origin wrote
#: them where a date was missing, and ``00/00/0000`` is a syntax error rather than a value.
_DATE_SHAPED_NULLS: frozenset[str] = frozenset({"00/00/0000", "0000-00-00", "00000000"})

#: The spellings the subject guard refuses as "the origin wrote nothing".
#:
#: A **declared subset** of the false nulls, and deliberately not the whole set: the guard's verdicts
#: are a measured behaviour (1.489 of the 8.155 real tags), so widening them would change which tags
#: reach the classifier. That is a classification decision, not a cleanup, and it does not belong in
#: a refactor.
_SUBJECT_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "não identificado",
        "não identificada",
        "local não identificado",
        "local não identificada",
        "localização não identificado",
        "localização não identificada",
        "sem identificação",
        "ilegível",
        "não possui",
        "não informado",
    }
)

#: Built from the spellings above, so the pattern cannot drift from the set it claims to implement.
#: The regex used to spell the variants out (``não identificad[oa]``); enumerating them is what makes
#: one definition possible.
_PLACEHOLDER_RE = re.compile(
    r"^(" + "|".join(re.escape(value) for value in sorted(_SUBJECT_PLACEHOLDERS)) + r")$",
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
    # The date parser accepts everything a text field refuses, plus the date-shaped placeholders.
    empty_date_values=_FALSE_NULL_VALUES | _DATE_SHAPED_NULLS,
    false_null_values=_FALSE_NULL_VALUES,
    untitled_title="SEM TÍTULO",
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
