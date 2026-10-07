"""
The collection vocabulary: the seed mirror, the lookup rule and the value object.

The mirror exists because a migration must keep describing the state it produced, so the seed is
duplicated on purpose and pinned here instead of trusted — the same pattern the NOBRADE ladder and
the subject drawers already follow. The rest of the file pins the two pure functions the proposal
and the guard read.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

from scrinalia.domains.archive.domain.collection_vocabulary import (
    ARRANGEMENT_TERMS,
    COLLECTION_TERMS,
    PLACE_KINDS,
    CollectionVocabulary,
    suggest_name,
    vocabulary_from_rows,
)

#: The repository root, derived from this file (testing/unit/archive/domain/).
_MIGRATIONS_DIR = Path(__file__).resolve().parents[4] / "migrations" / "versions"


def _load_migration(filename: str) -> ModuleType:
    """Loads a migration module by path, since ``migrations`` is not an importable package."""
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), _MIGRATIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheMigrationAndTheMirrorAgree:
    def test_the_arrangement_vocabulary_is_the_seeded_one(self) -> None:
        migration = _load_migration("b3d6f1a2c4e7_add_the_collection_vocabulary_catalogues.py")
        assert migration.ARRANGEMENT_TERMS == ARRANGEMENT_TERMS

    def test_the_collection_terms_are_the_seeded_ones(self) -> None:
        migration = _load_migration("b3d6f1a2c4e7_add_the_collection_vocabulary_catalogues.py")
        assert migration.COLLECTION_TERMS == COLLECTION_TERMS

    def test_every_seeded_kind_is_a_known_kind(self) -> None:
        """A kind the enum does not carry would fail the insert at migration time, not in a test."""
        from scrinalia.domains.archive.models.enums import CollectionTermKind

        known = {kind.value for kind in CollectionTermKind}
        assert {kind for _term, kind in COLLECTION_TERMS} <= known


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
