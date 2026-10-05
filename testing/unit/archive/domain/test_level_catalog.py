"""
The ladder of description levels, against the spellings the real collection declares.

The four values asserted here were read from the 3,608 descriptions of the acervo, with their
counts, because they are what the migration has to map: seeding the norm's wording
(``"Item documental"``) instead of the source's (``"Item Documental"``) would have failed 2,478
items on capitalisation alone.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from memoria_curitibana.domains.archive.domain.level_catalog import (
    NOBRADE_LEVELS,
    build_level_index,
    normalize_level_name,
    resolve_level_id,
)

_MIGRATIONS_DIR = Path(__file__).resolve().parents[4] / "migrations" / "versions"


def _load_migration(filename: str) -> ModuleType:
    """Loads a migration by path, since ``migrations`` is deliberately not an importable package."""
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), _MIGRATIONS_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _index() -> dict[str, int]:
    """The index the application builds from the seed constant, ids aside."""
    return build_level_index(
        (position, name, aliases) for position, _code, name, _description, aliases, _req, _allow in NOBRADE_LEVELS
    )


class TestTheSpellingsTheSourceDeclares:
    """Measured on the acervo: every one of the 3,608 descriptions must find its rung."""

    @pytest.mark.parametrize(
        "declared, expected_ordinal",
        [
            ("Item Documental", 5),
            ("Dossiê/Processo", 4),
            ("Seção", 2),
            ("Série", 3),
        ],
    )
    def test_each_declared_value_resolves_to_its_rung(self, declared: str, expected_ordinal: int) -> None:
        """The four values the collection declares, each landing on the rung it names."""
        assert resolve_level_id(_index(), declared) == expected_ordinal

    @pytest.mark.parametrize(
        "variant",
        [
            "dossie processo",
            "DOSSIE/PROCESSO",
            "  Dossiê/Processo  ",
            "Dossiê - Processo",
            "Dossiê — Processo",
            "Dossiê ou processo",
            "Dossiê",
            "Processo",
        ],
    )
    def test_the_fold_survives_case_accents_and_punctuation(self, variant: str) -> None:
        """All of these are the same rung: the punctuation may differ without the level changing."""
        assert resolve_level_id(_index(), variant) == resolve_level_id(_index(), "Dossiê/Processo")

    def test_an_unknown_spelling_resolves_to_nothing(self) -> None:
        """
        And that is the point: ``None`` is what lets the transfer record the node as unclassified
        instead of inventing a rung, while the human review refuses it outright.
        """
        assert resolve_level_id(_index(), "Nível Inventado") is None
        assert resolve_level_id(_index(), "") is None
        assert resolve_level_id(_index(), None) is None

    def test_the_canonical_name_wins_over_a_colliding_alias(self) -> None:
        """A curator registering a colliding alias must not steal another rung's matches."""
        index = build_level_index([(1, "Serie", []), (2, "Serie", [])])
        assert index[normalize_level_name("Serie")] == 1


class TestTheLadderItself:
    def test_the_ladder_has_the_six_nobrade_rungs_in_order(self) -> None:
        ordinals = [row[0] for row in NOBRADE_LEVELS]
        codes = [row[1] for row in NOBRADE_LEVELS]
        assert ordinals == [0, 1, 2, 3, 4, 5]
        assert codes == ["acervo", "fundo", "secao", "serie", "dossie", "item"]

    def test_the_item_is_a_leaf_and_the_obligatory_levels_need_a_parent(self) -> None:
        by_code = {row[1]: row for row in NOBRADE_LEVELS}
        # Dossiê and Item may not be roots; Item may not have children.
        assert by_code["dossie"][5] is True
        assert by_code["item"][5] is True
        assert by_code["item"][6] is False
        assert by_code["fundo"][6] is True

    def test_the_migration_and_the_code_agree(self) -> None:
        """
        The migration duplicates the ladder on purpose (replaying history must reproduce the state
        it produced), so the duplication is pinned here instead of trusted.
        """
        migration = _load_migration("a1f2c3d4e5b6_add_the_description_level_catalog.py")
        normalized = tuple((row[0], row[1], row[2], row[3], tuple(row[4]), row[5], row[6]) for row in migration.LEVELS)
        assert normalized == NOBRADE_LEVELS
