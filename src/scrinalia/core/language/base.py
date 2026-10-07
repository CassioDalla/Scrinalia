"""
The contract a language fulfils, and nothing else.

The rules that read a language are deliberately **not** here: ``staging/dates.py`` parses
dates, ``archive/domain/vocabulary.py`` guards terms, ``archive/domain/normalization.py``
singularises them, and the clustering and NER registries pick their models. Those rules
are the same whatever the language is; what changes is the data they read. Keeping the
data in one object per language is what lets a second language be added by writing a
profile instead of copying the rules.

A profile is frozen because it is a constant of the deployment, not state: nothing may
mutate the stopwords or the patterns of a running process.
"""

from dataclasses import dataclass
from re import Pattern


@dataclass(frozen=True)
class LanguageProfile:
    """Everything in the system that is a property of the language, and nothing else."""

    #: BCP-47-ish tag, the value ``ACERVO_LANGUAGE`` carries (``pt-BR``).
    code: str
    #: Human name, for a log line or a screen; never parsed.
    name: str

    #: Words the clustering engines discard before vectorizing.
    stopwords: frozenset[str]

    #: Spellings the origin wrote where there was no date at all (``00/00/0000``, ``sem data``).
    empty_date_values: frozenset[str]
    #: ``década de 1980`` / ``anos 90`` — the approximate decade expression.
    decade_pattern: Pattern[str]
    #: ``1951-1953`` / ``1920 a 2006`` — a range, joined by a language word or a dash.
    range_pattern: Pattern[str]
    #: The local date spelling (``dd/mm/yyyy`` in pt-BR); ``local_date_order`` names its groups.
    local_date_pattern: Pattern[str]
    #: Group order of ``local_date_pattern``: ``"DMY"`` for ``dd/mm/yyyy``, ``"MDY"`` for en-US.
    local_date_order: str
    #: A year outside this window is a code, not a date.
    min_year: int
    max_year: int
    #: A two-digit year is read as this century + the value (``90`` -> ``1990``).
    two_digit_year_base: int

    #: A placeholder such as ``local não identificado``: the origin's way of writing "empty".
    placeholder_pattern: Pattern[str]
    #: Street/address prefixes. A place, never a subject.
    street_pattern: Pattern[str]
    #: A bare number, optionally followed by a unit (``303 anos``).
    measure_pattern: Pattern[str]

    #: Regular plural endings mapped to the singular they may come from, for merge suggestions.
    plural_rules: tuple[tuple[str, str], ...]

    #: PostgreSQL text-search dictionary. The generated ``search_vector`` is built with it, so
    #: changing it is a schema change, not a reboot: ``alembic check`` reports the drift.
    fts_dictionary: str
    #: spaCy model the NER presets default to before any override.
    ner_model: str
