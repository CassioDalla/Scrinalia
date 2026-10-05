"""Pure rules of the archival arrangement tree (Fase 2.5, H2).

Nothing here touches the database. Whether a move is legal, how a materialised path is built
and which diagnostics a node carries are pure functions, so they are unit-testable without
Postgres and reusable by the API, the bench and the future curator UI.

Two axes are easy to confuse and this module keeps them apart on purpose:

* **hierarchy** is *provenance and arrangement*: who produced the record and how it was
  organised. It is objective, carried by the ``reference_code``, and a description lives in
  exactly **one** place in the tree;
* **macro category** is *subject*: what the record is about. It is interpretative, produced by
  the AI, and a description carries **several**.

The tree therefore groups by ``path`` and never by subject, and no rule below reads a macro
category.
"""

import enum
from collections.abc import Iterable
from dataclasses import dataclass

#: Separator of the materialised path. Kept a constant so the SQL that rewrites a subtree and
#: the Python that builds one cannot drift apart on a literal.
PATH_SEPARATOR = "."


class HierarchyViolation(enum.StrEnum):
    """
    Why a proposed parent/level assignment is refused.

    Codes rather than prose: the API translates them and the curator UI groups by them. The
    messages the archivist reads are built next to the response, never here.
    """

    SELF_PARENT = "SELF_PARENT"
    #: The new parent already lives under the node being moved (A under B while B is under A).
    CYCLE = "CYCLE"
    #: The child's level ordinals is not strictly greater than the parent's.
    LEVEL_NOT_ALLOWED_AS_CHILD = "LEVEL_NOT_ALLOWED_AS_CHILD"
    #: The parent's level is a leaf (``allows_children`` is false).
    PARENT_ALLOWS_NO_CHILDREN = "PARENT_ALLOWS_NO_CHILDREN"
    #: The level demands a parent (a Dossiê only exists under something) and none was given.
    REQUIRED_LEVEL_WITHOUT_PARENT = "REQUIRED_LEVEL_WITHOUT_PARENT"


class HierarchyIssue(enum.StrEnum):
    """
    What the diagnostics screen (H5) groups by.

    Computed on read from the tree and the codes: none of these is stored, because every one of
    them is a statement about the current state rather than a decision. Storing them would let
    them go stale the moment a node moves, which is the defect this phase exists to avoid.
    """

    #: ``parent_id IS NULL`` on a level that requires a parent (or simply has no parent yet).
    ORPHAN = "ORPHAN"
    #: The narrower, named case of ``ORPHAN``: an obligatory level (Dossiê) sitting at the root.
    DOSSIER_WITHOUT_PARENT = "DOSSIER_WITHOUT_PARENT"
    #: The materialised path disagrees with the parent's — the invariant is broken.
    PATH_DIVERGENCE = "PATH_DIVERGENCE"
    #: The declared level does not match the depth the reference code suggests.
    LEVEL_DEPTH_MISMATCH = "LEVEL_DEPTH_MISMATCH"
    #: A sibling whose code differs by almost nothing (``FOTOGRAFIA`` vs ``FOTOGRAFIAS``).
    NEAR_DUPLICATE_NODE = "NEAR_DUPLICATE_NODE"
    #: No level could be resolved from the declared text; the node has a level but no rung.
    UNKNOWN_LEVEL = "UNKNOWN_LEVEL"


class ProposalFlag(enum.StrEnum):
    """
    What the proposal has to say about a node it suggests — all of it advisory.

    Kept apart from ``HierarchyIssue`` because none of these describes the *stored* tree: a
    proposal is a reading of the reference codes, and every one of these flags exists so the
    archivist knows which parts of it are measured and which are a guess.
    """

    #: The ordinal was not taken from an existing record: it is a proposal, not a statement.
    ORDINAL_INFERRED = "ORDINAL_INFERRED"
    #: A record whose code is a pure arrangement rung and that has no document under it.
    RECORD_WITHOUT_DOCUMENTS = "RECORD_WITHOUT_DOCUMENTS"
    #: More than one record claims the same reference code, so "the" existing node is ambiguous.
    DUPLICATE_REFERENCE_CODE = "DUPLICATE_REFERENCE_CODE"


@dataclass(frozen=True)
class LevelRules:
    """The slice of a level the tree rules need, so the domain never imports the ORM."""

    level_id: int
    ordinal: int
    name: str
    requires_parent: bool
    allows_children: bool


@dataclass(frozen=True)
class NodeShape:
    """The slice of a description the tree rules need."""

    description_id: str
    parent_id: str | None
    path: str
    level: LevelRules | None = None


def build_path(parent_path: str | None, description_id: str) -> str:
    """
    Materialised path of a node, from its parent's.

    A root node's path is its own id, which is the base case the whole invariant rests on:
    ``path == parent.path + "." + id`` for every other node, and ``path == id`` for a root.
    Ids rather than reference codes, because a code may be corrected and a path must not have
    to follow it: the arrangement is expressed by the tree, not by the string.
    """
    if not parent_path:
        return description_id
    return f"{parent_path}{PATH_SEPARATOR}{description_id}"


def is_within(candidate_path: str, ancestor_path: str) -> bool:
    """True when ``candidate_path`` is the ancestor itself or a node below it."""
    return candidate_path == ancestor_path or candidate_path.startswith(f"{ancestor_path}{PATH_SEPARATOR}")


def would_create_cycle(node_path: str, new_parent_path: str | None) -> bool:
    """
    True when hanging a node under ``new_parent_path`` would close a loop.

    One line instead of a recursive walk because the path is materialised: if the target parent
    already lives under the node being moved, the node is its own ancestor.
    """
    if not new_parent_path:
        return False
    return is_within(new_parent_path, node_path)


def validate_assignment(
    description_id: str,
    node_path: str,
    new_parent: NodeShape | None,
    child_level: LevelRules | None,
) -> list[HierarchyViolation]:
    """
    Every rule a parent/level assignment must satisfy, as a list of codes.

    Returning the whole list rather than raising on the first violation lets the curator UI
    explain everything that is wrong in one pass. An unknown level (``None``) is not a
    violation: the level may simply not be classified yet, and the classifier is advisory.
    """
    violations: list[HierarchyViolation] = []

    if new_parent is None:
        if child_level is not None and child_level.requires_parent:
            violations.append(HierarchyViolation.REQUIRED_LEVEL_WITHOUT_PARENT)
        return violations

    if new_parent.description_id == description_id:
        violations.append(HierarchyViolation.SELF_PARENT)
        return violations

    if would_create_cycle(node_path, new_parent.path):
        violations.append(HierarchyViolation.CYCLE)

    parent_level = new_parent.level
    if parent_level is not None and not parent_level.allows_children:
        violations.append(HierarchyViolation.PARENT_ALLOWS_NO_CHILDREN)

    if child_level is not None and parent_level is not None and child_level.ordinal <= parent_level.ordinal:
        violations.append(HierarchyViolation.LEVEL_NOT_ALLOWED_AS_CHILD)

    return violations


def verify_path_invariant(nodes: list[NodeShape]) -> list[tuple[str, str]]:
    """
    Returns every ``(description_id, expected_path)`` whose materialised path diverged.

    The invariant is the promise the whole navigation rests on: a subtree query is a single
    ``LIKE 'x.%'``, and that is only correct while every path equals its parent's plus its own
    id. It runs in the CI over a fixture tree and against the real collection through the
    diagnostics endpoint, so a divergence is found by a check rather than by a wrong page.
    """
    by_id = {node.description_id: node for node in nodes}
    divergences: list[tuple[str, str]] = []

    for node in nodes:
        parent = by_id.get(node.parent_id) if node.parent_id else None
        expected = build_path(parent.path if parent else None, node.description_id)
        if node.path != expected:
            divergences.append((node.description_id, expected))

    return divergences


def dominant_ordinal_by_depth(observations: Iterable[tuple[int, int]]) -> dict[int, int]:
    """
    Learns which level each code depth is used for, from the collection itself.

    The roadmap asks for "profundidade do código ≠ ordinal" as a diagnostic, which presumes a
    depth-to-level mapping. The measurement says there is none to hardcode: five tokens hold
    2,466 Items, one Série and one Seção, and four tokens hold two Seções and two Séries. So the
    norm is **derived** instead of assumed — the modal level per depth — and only where it is a
    strict majority, so a tie (four tokens) yields no norm and flags nothing.

    That is what makes the diagnostic catch the real anomalies (an ``Item Documental`` among
    1,092 Dossiês at depth 8) without a single hand-written rule about which depth means what.
    """
    counts: dict[int, dict[int, int]] = {}
    for depth, ordinal in observations:
        counts.setdefault(depth, {})
        counts[depth][ordinal] = counts[depth].get(ordinal, 0) + 1

    norms: dict[int, int] = {}
    for depth, distribution in counts.items():
        total = sum(distribution.values())
        ordinal, hits = max(distribution.items(), key=lambda item: (item[1], -item[0]))
        if hits * 2 > total:
            norms[depth] = ordinal
    return norms


def decode_ordinal(levels_by_ordinal: dict[int, str], ordinal: int | None) -> str | None:
    """Name of the rung at ``ordinal``, so a diagnostic can be read without the catalogue."""
    if ordinal is None:
        return None
    return levels_by_ordinal.get(ordinal)


def near_duplicate_codes(codes: Iterable[str]) -> list[tuple[str, str]]:
    """
    Sibling codes that differ only by a trailing plural ``s``.

    This is the ``FOTOGRAFIA`` (2,391 items) versus ``FOTOGRAFIAS`` (the existing Série) case the
    roadmap warns about: the two are one letter apart and a trigram-based merge would happily join
    them, which is exactly why the tag-merge suggestion must never run over these codes. The rule
    here is deliberately narrower than a similarity score — same parent, same stem, one trailing
    ``s`` — because the point is to *flag* the pair for the archivist, not to score it.
    """
    by_parent: dict[str, dict[str, str]] = {}
    for code in codes:
        tokens = code.split(" ")
        if len(tokens) < 2:
            continue
        parent = " ".join(tokens[:-1])
        # Folded, because the comparison is about the word and not about how the source capitalised
        # it: ``CASA``/``CASAS`` is the same collision as ``FOTOGRAFIA``/``FOTOGRAFIAS``.
        by_parent.setdefault(parent, {})[tokens[-1].lower()] = code

    pairs: list[tuple[str, str]] = []
    for siblings in by_parent.values():
        for token, code in sorted(siblings.items()):
            singular = token[:-1] if token.endswith("s") else f"{token}s"
            counterpart = siblings.get(singular)
            if counterpart and counterpart != code:
                pairs.append((code, counterpart))

    # Each pair is seen from both ends; keep one.
    return sorted({tuple(sorted(pair)) for pair in pairs})  # type: ignore[return-value]
