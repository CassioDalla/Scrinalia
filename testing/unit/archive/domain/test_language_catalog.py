"""The language catalogue: a closed list, and the order the select shows."""

import unicodedata
from collections import Counter

from scrinalia.domains.archive.domain.language_catalog import LANGUAGES, Language


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
    assert LANGUAGES[0] == Language(code="pt", name="Português")


def test_the_rest_is_alphabetical_by_the_name_a_person_reads() -> None:
    """
    A catalogue of thirty names is read top to bottom, so the order after the first entry matters.

    Sorted the way a Portuguese dictionary would: ``Alemão`` before ``Árabe``, and ``Iídiche``
    before ``Inglês`` — the accented letter sorts as its base letter, not as its code point.
    """
    rest = [language.name for language in LANGUAGES[1:]]
    assert rest == sorted(rest, key=_readable_order)
