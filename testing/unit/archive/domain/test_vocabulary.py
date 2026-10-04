"""
The deterministic guard that keeps non-subjects out of the classifier.

Every spelling asserted here was read from the real collection, with its document count,
so the test fails if the rule stops covering what it was written for. The counts are the
evidence: ``1924`` reaches 260 documents and was classified as "Mobilidade e Transporte"
with **0.73** confidence, which is why no threshold could have caught it.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from memoria_curitibana.domains.archive.domain.vocabulary import (
    RETIRED_CATEGORIES,
    SUBJECT_CATEGORIES,
    is_measure,
    is_person_name,
    is_place_term,
    is_placeholder,
    is_street,
    is_subject_candidate,
    is_year,
)

#: The repository root, derived from this file (testing/unit/archive/domain/) so the test
#: does not depend on where pytest was invoked from.
_MIGRATIONS_DIR = Path(__file__).resolve().parents[4] / "migrations" / "versions"


def _load_migration(filename: str) -> ModuleType:
    """Loads a migration module by path, since ``migrations`` is not an importable package."""
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), _MIGRATIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestNonSubjectsMeasuredOnTheCollection:
    """The three families the classifier must never see, with the real document counts."""

    @pytest.mark.parametrize(
        "term, documents",
        [("1924", 260), ("1915", 223), ("1925", 178), ("1916", 79), ("1917", 73), ("1918", 45)],
    )
    def test_a_bare_year_is_not_a_subject(self, term: str, documents: int) -> None:
        assert is_year(term), f"{term} reaches {documents} documents and is a date, not a subject"
        assert not is_subject_candidate(term)

    @pytest.mark.parametrize(
        "term, documents",
        [
            ("local não identificado", 166),
            ("localização não identificada", 159),
            ("não identificado", 94),
            ("ilegível", 61),
        ],
    )
    def test_a_placeholder_is_not_a_subject(self, term: str, documents: int) -> None:
        assert is_placeholder(term), f"{term} reaches {documents} documents and carries no information"
        assert not is_subject_candidate(term)

    @pytest.mark.parametrize(
        "term, documents",
        [
            ("jaime lerner", 77),
            ("tadeusz kościuszko", 54),
            ("lina faria", 36),
            ("paulo spzak", 35),
        ],
    )
    def test_a_person_name_is_not_a_subject(self, term: str, documents: int) -> None:
        """A name is the producer, the same reasoning that retired the ``Instituição`` drawer."""
        assert is_person_name(term), f"{term} reaches {documents} documents and names a person"
        assert not is_subject_candidate(term)


class TestStreetsGoToTheFacetAndNotEmpty:
    """Decision of the product owner (2026-10-04): a street is a place, not silence."""

    @pytest.mark.parametrize(
        "term, documents",
        [
            ("rua xv de novembro", 118),
            ("rua engenheiro ostoja roguski", 75),
            ("avenida marechal floriano peixoto", 72),
            ("rua 24 de maio", 13),
            ("r. pres. carlos cavalcanti", 51),
            ("av. presidente affonso camargo", 43),
            ("alameda doutor muricy", 46),
            ("travessa nestor de castro", 17),
            ("rodovia br 116", 13),
        ],
    )
    def test_a_street_is_not_a_subject_but_is_a_place(self, term: str, documents: int) -> None:
        """
        The two answers differ on purpose: the street must not be classified *and* must not
        be discarded. A curator reading only ``is_subject_candidate`` would conclude that
        ``rua xv de novembro`` (118 documents) goes nowhere.
        """
        assert not is_subject_candidate(term), f"{term} reaches {documents} documents"
        assert is_place_term(term), f"{term} is a place and the facet is where it goes"

    def test_the_street_prefix_is_what_matters(self) -> None:
        """
        A bare ``rua`` (42 documents) and its plural ``ruas`` (8) are the street form, not a
        subject. The prefix is deliberately left open on the right so the plural is covered.
        """
        assert is_street("rua 24 de maio")
        assert is_street("br-116")
        assert is_street("rua")
        assert is_street("ruas")
        assert not is_street("ruído")

    def test_a_toponym_is_a_place_without_being_a_street(self) -> None:
        assert is_place_term("curitiba")
        assert is_place_term("centro")
        assert not is_street("curitiba")


class TestTheGuardDoesNotSwallowRealSubjects:
    """A guard that eats subjects is worse than no guard: it invents silence."""

    @pytest.mark.parametrize(
        "term, documents",
        [
            ("igrejas", 2467),
            ("residencial", 941),
            ("alvenaria", 826),
            ("casa", 387),
            ("linha férrea", 308),
            ("madeira", 283),
            ("eclético", 261),
            ("patrimônio histórico", 256),
            ("parque", 203),
            ("comércio", 193),
            ("jardim botânico", 201),
            ("canoagem", 78),
        ],
    )
    def test_a_real_subject_is_still_sent_to_the_classifier(self, term: str, documents: int) -> None:
        assert is_subject_candidate(term), f"{term} reaches {documents} documents and is a subject"

    def test_a_year_inside_a_phrase_is_not_a_bare_year(self) -> None:
        """``anos 90`` is a period the date parser handles, not a bare year."""
        assert not is_year("anos 90")
        assert is_year("1990")

    def test_a_number_with_a_unit_is_a_measure(self) -> None:
        """``303 anos`` is a length of time the origin put in a tag column, not a subject."""
        assert is_measure("303 anos")
        assert is_measure("950")
        assert not is_measure("br-116")
        assert not is_measure("igrejas")


class TestVocabularyShape:
    """The constants are the contract between the migration and the classifier."""

    def test_religion_exists_because_the_largest_tag_needed_it(self) -> None:
        """``igrejas`` reaches 2.467 documents: without this drawer the model has no answer."""
        assert "Religião" in SUBJECT_CATEGORIES

    def test_the_retired_drawers_are_not_subjects(self) -> None:
        """``Instituição`` and ``Localidade`` are provenance and geography; ``Pessoa`` a name."""
        assert "Instituição" in RETIRED_CATEGORIES
        assert "Localidade" in RETIRED_CATEGORIES
        assert "Pessoa" in RETIRED_CATEGORIES
        for retired in RETIRED_CATEGORIES:
            assert retired not in SUBJECT_CATEGORIES, f"{retired} cannot be in both axes"

    def test_no_drawer_without_evidence_survived(self) -> None:
        """``Saúde`` and ``Administração`` had zero tags in the collection and were dropped."""
        assert "Saúde" not in SUBJECT_CATEGORIES
        assert "Administração e Política Pública" not in SUBJECT_CATEGORIES

    def test_the_migration_and_the_code_agree(self) -> None:
        """
        The migration duplicates the list on purpose (replaying history must reproduce the
        state it produced), so the duplication is pinned here instead of trusted.

        Loaded by path rather than imported: ``alembic.ini`` sets ``prepend_sys_path`` to
        empty on purpose, so ``migrations`` is deliberately not an importable package.
        """
        migration = _load_migration("f8760cab6d12_replace_the_subject_vocabulary_and_.py")
        assert tuple(name for name, _description in migration.SUBJECT_CATEGORIES) == SUBJECT_CATEGORIES
        assert migration.RETIRED_CATEGORIES == RETIRED_CATEGORIES
