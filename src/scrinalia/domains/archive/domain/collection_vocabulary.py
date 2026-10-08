"""
The collection's own vocabulary: the value object the guard reads.

``CollectionVocabulary`` is the **runtime** input: a frozen pair of sets that the subject guard
consults for the two families the *collection* owns — a toponym it carries as a place and a person
name. The guard stays a pure function of the term plus this object, which is what keeps it
deterministic and testable; the repository loads the object from ``archive_collection_terms`` once
per run.

There is deliberately no seed here. The vocabulary is **data of the installation**, and the reference
collection's rows left the repository for the same reason the descriptions did: a clone must not
carry somebody's catalogue. A fresh install therefore starts with an empty vocabulary, and the guard
refuses nothing of its own — which is the correct answer and not a degraded one. An installation that
wants the vocabulary it came from loads it with
``python -m scrinalia.domains.archive.cli import``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from scrinalia.domains.archive.models.enums import PLACE_TERM_KINDS, CollectionTermKind


def normalize_term(term: str) -> str:
    """
    Canonical form of a collection term: whitespace collapsed, lowercase.

    The collapsed whitespace is not cosmetic: a term copied from a page arrives with a double space
    often enough that ``local  não identificado`` and ``local não identificado`` were two rows the
    curator could not tell apart, and only one of them matched.
    """
    return " ".join(term.split()).lower()


@dataclass(frozen=True)
class CollectionVocabulary:
    """
    The terms the collection declares, split by where the guard sends them.

    ``place_terms`` claim the PLACE facet; ``person_terms`` go nowhere (the name is the producer,
    the same reasoning that retired the ``Pessoa`` drawer). Both are stored normalised, and the
    default is empty: an installation with no catalogue refuses nothing it has not declared,
    which is the honest behaviour for a collection nobody has described yet.
    """

    place_terms: frozenset[str] = field(default_factory=frozenset)
    person_terms: frozenset[str] = field(default_factory=frozenset)

    def is_place(self, term: str) -> bool:
        return normalize_term(term) in self.place_terms

    def is_person(self, term: str) -> bool:
        return normalize_term(term) in self.person_terms


#: The vocabulary of a deployment whose catalogue is still empty. Never a fallback to the
#: reference collection: that would make another institution's installation silently Curitiba.
EMPTY_VOCABULARY = CollectionVocabulary()

#: The kinds that claim the PLACE facet, as stored values. Derived from the enum so the catalogue
#: and the guard cannot disagree about which kind is a place.
PLACE_KINDS: frozenset[str] = frozenset(kind.value for kind in PLACE_TERM_KINDS)


def vocabulary_from_rows(rows: list[tuple[str, str]]) -> CollectionVocabulary:
    """Builds the guard's value object from ``(term, kind)`` pairs, active rows only."""
    places: set[str] = set()
    persons: set[str] = set()
    for term, kind in rows:
        if kind in PLACE_KINDS:
            places.add(normalize_term(term))
        elif kind == CollectionTermKind.PERSON.value:
            persons.add(normalize_term(term))
    return CollectionVocabulary(place_terms=frozenset(places), person_terms=frozenset(persons))


def suggest_name(code: str, names: Mapping[str, str]) -> str | None:
    """
    The suggestion for a rung's code: the whole code first, then its last token.

    ``BR PRADAP`` is the collection's root and has a name of its own; ``IPPUC`` is a token that
    names the fund. Looking the whole code up first is what lets the two coexist in one
    catalogue, and it is the rule the old two-dict constant implemented by hand.
    """
    if code in names:
        return names[code]
    return names.get(code.split(" ")[-1])


#: The guard's five verdicts, as codes. Declared once because the suggestion route publishes
#: them and the screen translates them: a bare string in two places would drift.
SUBJECT_EXCLUSION_SIGNALS: tuple[str, ...] = ("PLACEHOLDER", "YEAR", "MEASURE", "STREET", "PERSON")
