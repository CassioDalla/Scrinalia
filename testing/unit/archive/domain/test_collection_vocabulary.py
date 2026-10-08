"""
The collection vocabulary: the lookup rule and the value object.

There is nothing left to pin against a migration: the catalogue is **data of the installation**, the
seed left ``src/``, and the tests carry the reference collection's rows as fixture data instead
(``testing/reference_vocabulary.py`` explains why they may). What is left to test is the rule itself
and the two pure functions the proposal and the guard read.
"""

from scrinalia.domains.archive.domain.collection_vocabulary import (
    PLACE_KINDS,
    CollectionVocabulary,
    suggest_name,
    vocabulary_from_rows,
)


class TestSuggestName:
    """The rule the old two-dict constant implemented by hand."""

    def test_the_whole_code_wins_over_its_last_token(self) -> None:
        names = {"BR PRADAP": "Acervo", "PRADAP": "Instituto"}
        assert suggest_name("BR PRADAP", names) == "Acervo"

    def test_it_falls_back_to_the_last_token(self) -> None:
        assert suggest_name("BR PRADAP SMU ED", {"ED": "Edificações"}) == "Edificações"

    def test_an_unknown_code_suggests_nothing(self) -> None:
        """No name is better than the wrong name: the archivist writes it."""
        assert suggest_name("BR OUTRA COISA", {"ED": "Edificações"}) is None


class TestVocabularyFromRows:
    def test_it_splits_places_from_persons(self) -> None:
        vocabulary = vocabulary_from_rows([("centro", "DISTRICT"), ("jaime lerner", "PERSON")])
        assert vocabulary.is_place("centro")
        assert vocabulary.is_person("jaime lerner")
        assert not vocabulary.is_place("jaime lerner")
        assert not vocabulary.is_person("centro")

    def test_every_place_kind_claims_the_facet(self) -> None:
        for kind in PLACE_KINDS:
            vocabulary = vocabulary_from_rows([("algum lugar", kind)])
            assert vocabulary.is_place("algum lugar"), f"{kind} é um lugar"

    def test_the_lookup_is_case_and_space_insensitive(self) -> None:
        """The spellings arrive from a page: ``Centro`` and ``centro`` are the same place."""
        vocabulary = vocabulary_from_rows([("centro cívico", "DISTRICT")])
        assert vocabulary.is_place("  Centro   Cívico ")

    def test_an_empty_catalogue_claims_nothing(self) -> None:
        empty = CollectionVocabulary()
        assert not empty.is_place("curitiba")
        assert not empty.is_person("jaime lerner")
