"""The languages a description may declare, declared once and read by every surface.

A description's language is a closed list — ``Português``, ``Latim``, ``Nheengatu`` — and it is
**not** institution data the archivist invents, the way a typology or an arrangement rung is. So it
lives here, in code, beside the level ladder's own normalisation and the origin registry, instead of
in a catalogue table with its own screen: there is no rule attached to a language (a rung has
``requires_parent``; a language has nothing), no candidate label for an engine, and no facet that
filters by it yet. A facet is the trigger to make it a table.

The stored value is the **name**, not the code: ``archive_documents.language_name`` is free text from
the origins, and turning it into a foreign key would need a backfill fold like the level's, without
buying anything today. The code travels with each entry because a second surface (the public site, a
future i18n) reads it, and because it is the stable identifier if the names are ever translated — the
name is what the archivist reads, the code is what a program keys on.

**One language, one spelling.** The origins do not agree on how to write a language, and the
reference collection measured it: 78 descriptions declared ``Português Brasil`` and 22 declared
``Português/Brasil`` — two spellings of one language, both rendered as unknown by a dossier that
compares strings. The entries below carry the variants (``aliases``), and :func:`resolve_language`
folds a declared spelling to the catalogue's name; a spelling that does not resolve is kept verbatim,
because a catalogue must never replace what a source said with a guess.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

#: ``/``, ``\``, en dash, em dash and hyphen separate the words of a language in the source
#: spellings (``Português/Brasil``, ``PT-BR``), so they collapse to a single space before the
#: comparison — the same class the level ladder folds with.
_SEPARATORS = re.compile(r"[/\\\-\u2013\u2014]+")
_WHITESPACE = re.compile(r"\s+")

#: The variants a source may declare for its language. The fold already survives case and accents
#: (``inglês``, ``INGLES`` and ``Inglês`` are one key), so an alias is only for a *different word* or
#: an abbreviation: ``English``, ``Port.``, ``Español``.
_ALIASES: dict[str, tuple[str, ...]] = {
    "Português": ("Português Brasil", "Português/Brasil", "Português do Brasil", "PT-BR", "PT", "Port."),
    "Inglês": ("English", "Ing."),
    "Espanhol": ("Castelhano", "Español", "Esp."),
    "Francês": ("Français",),
    "Alemão": ("Deutsch", "German"),
    "Latim": ("Latin",),
    "Grego": ("Greek",),
    "Hebraico": ("Hebrew",),
    "Holandês": ("Dutch", "Neerlandês"),
    "Húngaro": ("Hungarian",),
    "Iídiche": ("Yiddish",),
    "Japonês": ("Japanese",),
    "Chinês": ("Chinese",),
    "Coreano": ("Korean",),
    "Norueguês": ("Norwegian",),
    "Polonês": ("Polish", "Polaco"),
    "Romeno": ("Romanian",),
    "Russo": ("Russian",),
    "Sueco": ("Swedish",),
    "Tcheco": ("Czech", "Checo"),
    "Turco": ("Turkish",),
    "Ucraniano": ("Ukrainian",),
    "Árabe": ("Arabic", "Arabe"),
}


@dataclass(frozen=True)
class Language:
    """One language of the catalogue: the ISO 639 code, the Portuguese name and its variants."""

    code: str
    name: str
    aliases: tuple[str, ...] = field(default=())


#: The catalogue, in the order a select shows it: the collection's own language first, then the rest
#: alphabetically. The list is deliberately short — the languages an archive in this country
#: plausibly holds — and additive: a new entry is a line here and a test, never a migration.
LANGUAGES: tuple[Language, ...] = (
    Language("pt", "Português", _ALIASES["Português"]),
    Language("de", "Alemão", _ALIASES["Alemão"]),
    Language("ar", "Árabe", _ALIASES["Árabe"]),
    Language("zh", "Chinês", _ALIASES["Chinês"]),
    Language("ko", "Coreano", _ALIASES["Coreano"]),
    Language("es", "Espanhol", _ALIASES["Espanhol"]),
    Language("fr", "Francês", _ALIASES["Francês"]),
    Language("el", "Grego", _ALIASES["Grego"]),
    Language("gn", "Guarani"),
    Language("he", "Hebraico", _ALIASES["Hebraico"]),
    Language("nl", "Holandês", _ALIASES["Holandês"]),
    Language("hu", "Húngaro", _ALIASES["Húngaro"]),
    Language("yi", "Iídiche", _ALIASES["Iídiche"]),
    Language("en", "Inglês", _ALIASES["Inglês"]),
    Language("it", "Italiano"),
    Language("ja", "Japonês", _ALIASES["Japonês"]),
    Language("la", "Latim", _ALIASES["Latim"]),
    Language("yrl", "Nheengatu"),
    Language("no", "Norueguês", _ALIASES["Norueguês"]),
    Language("pl", "Polonês", _ALIASES["Polonês"]),
    Language("ro", "Romeno", _ALIASES["Romeno"]),
    Language("ru", "Russo", _ALIASES["Russo"]),
    Language("sv", "Sueco", _ALIASES["Sueco"]),
    Language("cs", "Tcheco", _ALIASES["Tcheco"]),
    Language("tr", "Turco", _ALIASES["Turco"]),
    Language("uk", "Ucraniano", _ALIASES["Ucraniano"]),
)


def normalize_language(value: str) -> str:
    """
    Folds a language spelling to the form the catalogue matches on.

    ``"Português/Brasil"``, ``"portugues brasil"`` and ``"PORTUGUÊS BRASIL"`` all fold to
    ``"portugues brasil"``: the comparison has to survive the punctuation, the accents and the case
    the source happens to use, because all three vary in real payloads. The same fold the level
    ladder uses, for the same reason.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_separators = _SEPARATORS.sub(" ", without_accents)
    return _WHITESPACE.sub(" ", without_separators).strip().lower()


def build_language_index(languages: Iterable[tuple[str, str, Sequence[str]]]) -> dict[str, str]:
    """
    Builds the ``folded spelling -> catalogue name`` index the resolution reads.

    The canonical ``name`` wins over an alias or a code that fold to the same key, so a variant
    registered by mistake cannot silently steal another language's matches. The order is deliberate:
    names first, then aliases, then codes.
    """
    index: dict[str, str] = {}
    entries = tuple(languages)
    for _code, name, _aliases in entries:
        index.setdefault(normalize_language(name), name)
    for _code, name, aliases in entries:
        for alias in aliases:
            index.setdefault(normalize_language(alias), name)
    for code, name, _aliases in entries:
        index.setdefault(normalize_language(code), name)
    return index


#: The index the transform reads, built once from the catalogue above.
LANGUAGE_INDEX: dict[str, str] = build_language_index(
    (language.code, language.name, language.aliases) for language in LANGUAGES
)


def resolve_language(declared: str | None, index: dict[str, str] | None = None) -> str | None:
    """
    The catalogue's spelling of a declared language, or ``None`` when the catalogue does not know it.

    ``None`` is the point: the transform keeps the declared text when this answers nothing, so a
    language the catalogue has never heard of is shown as the source wrote it instead of being
    replaced by the closest entry. An empty value stays empty.
    """
    if not declared:
        return None
    return (LANGUAGE_INDEX if index is None else index).get(normalize_language(declared))
