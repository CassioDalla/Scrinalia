"""The language catalogue: a closed list, the order the select shows, and the fold (#203)."""

import importlib.util
import unicodedata
from collections import Counter
from pathlib import Path
from types import ModuleType

import pytest

from scrinalia.domains.archive.domain.language_catalog import (
    LANGUAGES,
    build_language_index,
    normalize_language,
    resolve_language,
)

_MIGRATIONS_DIR = Path(__file__).resolve().parents[4] / "migrations" / "versions"


def _load_migration(filename: str) -> ModuleType:
    """Loads a migration by path, since ``migrations`` is deliberately not an importable package."""
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), _MIGRATIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _readable_order(name: str) -> str:
    """The key a person's eye uses: accents sort as their base letter, like a Portuguese dictionary."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def test_the_catalogue_is_well_formed() -> None:
    """
    Every entry has a unique code and a unique name, and none is blank.

    The code and the name are two identifiers of the same thing: a duplicate would make the select
    offer the same option twice, and a blank name would render an empty row the archivist cannot
    choose.
    """
    codes = Counter(language.code for language in LANGUAGES)
    names = Counter(language.name for language in LANGUAGES)

    assert [code for code, count in codes.items() if count > 1] == []
    assert [name for name, count in names.items() if count > 1] == []
    assert all(language.code.strip() and language.name.strip() for language in LANGUAGES)


def test_the_collections_own_language_comes_first() -> None:
    """The select is ordered by usefulness, not alphabetically: Portuguese is what most records are."""
    first = LANGUAGES[0]
    assert (first.code, first.name) == ("pt", "Português")


def test_the_rest_is_alphabetical_by_the_name_a_person_reads() -> None:
    """
    A catalogue of thirty names is read top to bottom, so the order after the first entry matters.

    Sorted the way a Portuguese dictionary would: ``Alemão`` before ``Árabe``, and ``Iídiche``
    before ``Inglês`` — the accented letter sorts as its base letter, not as its code point.
    """
    rest = [language.name for language in LANGUAGES[1:]]
    assert rest == sorted(rest, key=_readable_order)


# ------------------------------------------
# ONE LANGUAGE, ONE SPELLING (#203)
# ------------------------------------------

#: The spellings the reference collection really declares, plus the variants a source produces.
#: Measured before #203: ``Português Brasil`` in 78 descriptions and ``Português/Brasil`` in 22.
MEASURED_SPELLINGS = (
    "Português Brasil",
    "Português/Brasil",
    "Português do Brasil",
    "portugues brasil",
    "PORTUGUÊS BRASIL",
    "Português",
    "portugues",
    "PORTUGUÊS",
    "PT-BR",
    "pt",
    "Port.",
)


@pytest.mark.parametrize("declared", MEASURED_SPELLINGS)
def test_every_declared_spelling_reaches_the_catalogue(declared: str) -> None:
    """The fold survives the case, the accent and the punctuation the source happens to use."""
    assert resolve_language(declared) == "Português"


def test_an_unknown_language_is_not_guessed() -> None:
    """
    ``None`` is what lets the transfer keep the source's text.

    The catalogue must not replace a language it has never heard of by the closest entry: the dossier
    shows the declared text and marks it, and a guess there would be data nobody wrote.
    """
    assert resolve_language("Linguagem Inventada") is None
    assert resolve_language("") is None
    assert resolve_language(None) is None


def test_a_name_wins_over_an_alias_and_a_code() -> None:
    """The order is names, then aliases, then codes, so a bad alias cannot steal a language."""
    index = build_language_index([("xx", "Português", ("Inglês",)), ("yy", "Inglês", ())])

    assert index[normalize_language("Inglês")] == "Inglês"
    assert index[normalize_language("portugues")] == "Português"


def test_no_alias_of_one_language_is_the_name_of_another() -> None:
    """
    A duplicate alias is a silent steal: the first entry wins and the second language loses a match.

    The catalogue is small and hand-written, so the collision is caught here rather than discovered
    in a dossier showing an English record as Portuguese.
    """
    names = {normalize_language(language.name): language.name for language in LANGUAGES}
    stolen: list[str] = []
    for language in LANGUAGES:
        for alias in language.aliases:
            owner = names.get(normalize_language(alias))
            if owner is not None and owner != language.name:
                stolen.append(f"{alias!r} ({language.name}) é o nome de {owner}")
    assert stolen == []


def test_the_migration_and_the_code_agree() -> None:
    """
    The migration duplicates the catalogue on purpose (replaying history must reproduce the state it
    produced), so the duplication is pinned here instead of trusted.
    """
    migration = _load_migration("6c46426b048a_fold_the_language_spelling.py")
    # The mapping, not the order: the catalogue's order is what the select shows, and the migration
    # only needs to answer "which name owns this spelling".
    folded_by_the_migration = {name: tuple(aliases) for name, aliases in migration.LANGUAGES}
    expected = {language.name: language.aliases for language in LANGUAGES}

    assert folded_by_the_migration == expected
