"""The languages a description may declare, declared once and read by every surface.

A description's language is a closed list — ``Português``, ``Latim``, ``Nheengatu`` — and it is
**not** institution data the archivist invents, the way a typology or an arrangement rung is. So it
lives here, in code, beside the level ladder's own normalisation and the origin registry, instead of
in a catalogue table with its own screen: there is no rule attached to a language (a rung has
``requires_parent``; a language has nothing), no candidate label for an engine, and no facet that
filters by it yet. A facet is the trigger to make it a table.

The stored value is the **name**, not the code: ``archive_documents.language_name`` is free text from
the origins ("Português", "port."), and turning it into a foreign key would need a backfill fold like
the level's, without buying anything today. The code travels with each entry because a second surface
(the public site, a future i18n) reads it, and because it is the stable identifier if the names are
ever translated — the name is what the archivist reads, the code is what a program keys on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    """One language of the catalogue: the ISO 639 code and the Portuguese name a person reads."""

    code: str
    name: str


#: The catalogue, in the order a select shows it: the collection's own language first, then the rest
#: alphabetically. The list is deliberately short — the languages an archive in this country
#: plausibly holds — and additive: a new entry is a line here and a test, never a migration.
LANGUAGES: tuple[Language, ...] = (
    Language("pt", "Português"),
    Language("de", "Alemão"),
    Language("ar", "Árabe"),
    Language("zh", "Chinês"),
    Language("ko", "Coreano"),
    Language("es", "Espanhol"),
    Language("fr", "Francês"),
    Language("el", "Grego"),
    Language("gn", "Guarani"),
    Language("he", "Hebraico"),
    Language("nl", "Holandês"),
    Language("hu", "Húngaro"),
    Language("yi", "Iídiche"),
    Language("en", "Inglês"),
    Language("it", "Italiano"),
    Language("ja", "Japonês"),
    Language("la", "Latim"),
    Language("yrl", "Nheengatu"),
    Language("no", "Norueguês"),
    Language("pl", "Polonês"),
    Language("ro", "Romeno"),
    Language("ru", "Russo"),
    Language("sv", "Sueco"),
    Language("cs", "Tcheco"),
    Language("tr", "Turco"),
    Language("uk", "Ucraniano"),
)
