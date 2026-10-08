"""
The rules of the arrangement: pure, and measured against the real collection's shape.

The two functions that carry the measurement are ``dominant_ordinal_by_depth`` and
``near_duplicate_codes``. The first exists because the roadmap's "profundidade do código ≠ ordinal"
presumes a depth-to-level mapping that the data does not have — five tokens hold 2,466 Items, one
Série and one Seção at once — so the norm is learned and only where it is a strict majority. The
second exists because ``FOTOGRAFIA`` and ``FOTOGRAFIAS`` are one letter apart and a similarity
score would join them.
"""

from typing import ClassVar

import pytest

from scrinalia.domains.archive.domain.hierarchy import (
    HierarchyViolation,
    LevelRules,
    NodeShape,
    ancestor_rungs,
    build_path,
    collapse_chain,
    dominant_ordinal_by_depth,
    is_within,
    near_duplicate_codes,
    parent_rung_code,
    resolve_rung,
    validate_assignment,
    verify_path_invariant,
    would_create_cycle,
)

ITEM = LevelRules(level_id=6, ordinal=5, name="Item Documental", requires_parent=True, allows_children=False)
DOSSIER = LevelRules(level_id=5, ordinal=4, name="Dossiê/Processo", requires_parent=True, allows_children=True)
SERIES = LevelRules(level_id=4, ordinal=3, name="Série", requires_parent=False, allows_children=True)
FUND = LevelRules(level_id=2, ordinal=1, name="Fundo", requires_parent=False, allows_children=True)


def _node(description_id: str, path: str, parent_id: str | None = None, level: LevelRules | None = None) -> NodeShape:
    return NodeShape(description_id=description_id, parent_id=parent_id, path=path, level=level)


class TestPaths:
    def test_a_root_path_is_its_own_id(self) -> None:
        """The base case the whole invariant rests on."""
        assert build_path(None, "2368") == "2368"
        assert build_path("", "2368") == "2368"

    def test_a_child_extends_its_parent(self) -> None:
        assert build_path("2368", "2732") == "2368.2732"
        assert build_path("2368.2732", "51931") == "2368.2732.51931"

    @pytest.mark.parametrize(
        "candidate, ancestor, expected",
        [
            ("2368", "2368", True),
            ("2368.2732", "2368", True),
            ("2368.2732.51931", "2368", True),
            ("23681", "2368", False),
            ("236", "2368", False),
            ("2732", "2368", False),
        ],
    )
    def test_membership_is_by_path_segment_not_by_string_prefix(
        self, candidate: str, ancestor: str, expected: bool
    ) -> None:
        """``23681`` must not count as a descendant of ``2368``: the separator is what delimits."""
        assert is_within(candidate, ancestor) is expected

    def test_moving_a_node_under_its_own_descendant_is_a_cycle(self) -> None:
        assert would_create_cycle("2368", "2368.2732") is True
        assert would_create_cycle("2368", "2368") is True
        assert would_create_cycle("2368.2732", "2368") is False
        assert would_create_cycle("2368", None) is False


class TestValidation:
    def test_a_fund_may_be_a_root(self) -> None:
        assert validate_assignment("1", "1", None, FUND) == []

    def test_an_item_may_not_be_a_root(self) -> None:
        """NOBRADE is explicit: an item only exists under something."""
        assert HierarchyViolation.REQUIRED_LEVEL_WITHOUT_PARENT in validate_assignment("1", "1", None, ITEM)

    def test_an_item_may_not_receive_children(self) -> None:
        parent = _node("1", "1", level=ITEM)
        violations = validate_assignment("2", "2", parent, DOSSIER)
        assert HierarchyViolation.PARENT_ALLOWS_NO_CHILDREN in violations

    def test_a_child_must_sit_below_its_parent_on_the_ladder(self) -> None:
        parent = _node("1", "1", level=SERIES)
        assert HierarchyViolation.LEVEL_NOT_ALLOWED_AS_CHILD in validate_assignment("2", "2", parent, SERIES)

    def test_a_node_cannot_be_its_own_parent(self) -> None:
        parent = _node("1", "1", level=FUND)
        assert validate_assignment("1", "1", parent, SERIES) == [HierarchyViolation.SELF_PARENT]

    def test_a_cycle_is_refused(self) -> None:
        parent = _node("2", "1.2", level=SERIES)
        assert HierarchyViolation.CYCLE in validate_assignment("1", "1", parent, FUND)

    def test_every_violation_is_reported_not_only_the_first(self) -> None:
        """The curator UI explains the whole problem in one pass."""
        parent = _node("1", "1.2", level=ITEM)
        violations = validate_assignment("1", "1", parent, ITEM)
        assert violations == [HierarchyViolation.SELF_PARENT]

    def test_an_unknown_level_is_not_a_violation(self) -> None:
        """An unclassified level is advisory: it cannot be judged, and must not block a move."""
        parent = _node("1", "1", level=None)
        assert validate_assignment("2", "2", parent, None) == []


class TestTheInvariant:
    def test_a_consistent_tree_has_no_divergence(self) -> None:
        nodes = [
            _node("1", "1"),
            _node("2", "1.2", parent_id="1"),
            _node("3", "1.2.3", parent_id="2"),
        ]
        assert verify_path_invariant(nodes) == []

    def test_a_stale_path_is_found(self) -> None:
        nodes = [
            _node("1", "1"),
            _node("2", "1.2", parent_id="1"),
            # The parent moved and nobody rewrote this row.
            _node("3", "9.2.3", parent_id="2"),
        ]
        assert verify_path_invariant(nodes) == [("3", "1.2.3")]

    def test_a_root_with_a_foreign_path_is_found(self) -> None:
        assert verify_path_invariant([_node("1", "9.1")]) == [("1", "1")]


class TestDepthNormalisationIsLearnedNotAssumed:
    """The measured distribution of the real collection, reduced to its shape."""

    #: depth -> ordinal, exactly as the acervo distributes it.
    MEASURED = (
        [(4, 2)] * 2
        + [(4, 3)] * 2  # four tokens: a tie between Seção and Série
        + [(5, 5)] * 2466
        + [(5, 3)] * 1
        + [(5, 2)] * 1  # five tokens: the overwhelming majority is Item
        + [(6, 4)] * 2
        + [(6, 5)] * 1  # the anomaly
        + [(8, 4)] * 1092
        + [(8, 5)] * 10  # ten Items where 1,092 Dossiês live
    )

    def test_a_strict_majority_becomes_the_norm(self) -> None:
        norms = dominant_ordinal_by_depth(self.MEASURED)
        assert norms[5] == 5
        assert norms[6] == 4
        assert norms[8] == 4

    def test_a_tie_yields_no_norm_so_nothing_is_flagged(self) -> None:
        """Four tokens hold two Seções and two Séries: there is no norm to violate."""
        assert 4 not in dominant_ordinal_by_depth(self.MEASURED)

    def test_the_anomalies_are_the_minority_at_their_depth(self) -> None:
        norms = dominant_ordinal_by_depth(self.MEASURED)
        mismatches = [
            (depth, ordinal) for depth, ordinal in self.MEASURED if depth in norms and norms[depth] != ordinal
        ]
        # One Item at depth 6 and ten at depth 8, plus the one Série and one Seção at depth 5.
        assert len(mismatches) == 13

    def test_an_empty_observation_set_yields_no_norms(self) -> None:
        assert dominant_ordinal_by_depth([]) == {}


class TestNearDuplicates:
    def test_the_plural_singular_pair_is_found(self) -> None:
        """
        The ``FOTOGRAFIA`` (singular, 2,391 items) versus ``FOTOGRAFIAS`` (the Série) case.

        The pair is reported for the archivist; the code never decides which one survives.
        """
        pairs = near_duplicate_codes(["BR PRADAP IPPUC FOTOGRAFIA", "BR PRADAP IPPUC FOTOGRAFIAS", "BR PRADAP SMU ED"])
        assert pairs == [("BR PRADAP IPPUC FOTOGRAFIA", "BR PRADAP IPPUC FOTOGRAFIAS")]

    def test_siblings_under_different_parents_are_not_a_pair(self) -> None:
        assert near_duplicate_codes(["BR PRADAP IPPUC FOTOGRAFIA", "BR PRADAP SMMA FOTOGRAFIAS"]) == []

    def test_unrelated_siblings_are_not_a_pair(self) -> None:
        assert near_duplicate_codes(["BR PRADAP SMU ED", "BR PRADAP SMU AL"]) == []

    def test_each_pair_is_reported_once(self) -> None:
        pairs = near_duplicate_codes(["A B CASA", "A B CASAS"])
        assert len(pairs) == 1


class TestTheCollapseTheCodeCannotDo:
    """
    The archivist's correction, and the reason the plan catalogue exists.

    ``BR PRADAP SMU ED AL`` and ``BR PRADAP SMU ED AL CONSTR`` are, in the real arrangement, **one**
    level ("Alvenaria - Construções"). Nothing in the string says so: the code splits it into two
    alphabetic segments and the slicer has no way to know they are one rung. A person says it, and
    this is the machinery that follows what they said.
    """

    COLLAPSE: ClassVar[dict[str, str]] = {"BR PRADAP SMU ED AL CONSTR": "BR PRADAP SMU ED AL"}

    def test_the_link_is_followed_to_its_end(self) -> None:
        assert collapse_chain("BR PRADAP SMU ED AL CONSTR", self.COLLAPSE) == "BR PRADAP SMU ED AL"
        assert collapse_chain("BR PRADAP SMU ED AL", self.COLLAPSE) == "BR PRADAP SMU ED AL"
        assert collapse_chain("BR PRADAP IPPUC", self.COLLAPSE) == "BR PRADAP IPPUC"

    def test_a_chain_of_links_is_followed_all_the_way(self) -> None:
        chain = {"BR A B C": "BR A B", "BR A B": "BR A"}
        assert collapse_chain("BR A B C", chain) == "BR A"

    def test_a_contradictory_pair_does_not_loop_forever(self) -> None:
        ring = {"BR A B": "BR A B C", "BR A B C": "BR A B"}
        assert collapse_chain("BR A B", ring) in {"BR A B", "BR A B C"}

    def test_a_code_resolves_up_to_the_nearest_approved_rung(self) -> None:
        """A rung the archivist rejected means "this code lies, hang it higher"."""
        approved = {"BR PRADAP", "BR PRADAP SMU"}
        assert resolve_rung("BR PRADAP SMU ED AL CONSTR", {}, approved) == "BR PRADAP SMU"

    def test_the_collapse_can_carry_a_code_onto_an_approved_sibling(self) -> None:
        approved = {"BR PRADAP", "BR PRADAP IPPUC FOTOGRAFIAS"}
        collapse = {"BR PRADAP IPPUC FOTOGRAFIA": "BR PRADAP IPPUC FOTOGRAFIAS"}
        assert resolve_rung("BR PRADAP IPPUC FOTOGRAFIA", collapse, approved) == "BR PRADAP IPPUC FOTOGRAFIAS"

    def test_nothing_approved_on_the_path_means_no_target(self) -> None:
        assert resolve_rung("BR PRADAP SMU ED AL", {}, set()) is None

    def test_the_parent_of_a_rung_is_structural(self) -> None:
        assert parent_rung_code("BR PRADAP SMU ED") == "BR PRADAP SMU"
        assert parent_rung_code("BR PRADAP") is None

    def test_the_ancestors_are_every_strict_prefix_longest_first(self) -> None:
        assert ancestor_rungs("BR PRADAP SMU ED") == ("BR PRADAP SMU", "BR PRADAP")
