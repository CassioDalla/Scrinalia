"""
Pure rules of the entity merge.

An entity merge is one operation in two halves — a plan that describes the impact and an apply
that executes it — and the warnings the archivist must read before approving belong to neither
half alone: they are the vocabulary the dry run, the write and the screen share, so the number
the preview promises cannot be a different number from the one the merge writes.

The flags mirror the tag merge's (:mod:`scrinalia.domains.archive.domain.tag_merge`), with the
two that are specific to this axis: a cluster can mix ``ORG``/``PER``/``LOC``, and the optional
rename of the canonical is part of the same write.
"""

from dataclasses import dataclass

#: The absorbed member carries a type different from the canonical's. The spellings become
#: synonyms of the canonical's category, so a ``PER`` name absorbed into an ``ORG`` starts
#: resolving as an organisation — a decision the archivist has to see before the click.
REVIEW_MIXED_TYPES = "MIXED_TYPES"

#: The absorbed (or renamed-from) spelling is already a synonym of another entity, so two
#: decisions would compete over it.
REVIEW_MEMBER_IS_SYNONYM = "MEMBER_IS_SYNONYM"

#: The member carries a number. Measured on the tag axis, near-identical spellings with
#: different numbers are different subjects (``rua 24 de maio`` <- ``rua 13 de maio``); the
#: flag asks for a human look and never rejects anything on its own.
REVIEW_MEMBER_WITH_DIGITS = "MEMBER_WITH_DIGITS"

#: The absorbed entity carries no description. Absorbing it loses no link, but it is the class
#: of row the orphan purge targets, and it is worth telling apart from a name the collection uses.
REVIEW_ORPHAN_MEMBER = "ORPHAN_MEMBER"

#: The two writes the entity ledger records. A merge absorbs an entity and brings it back on undo; a
#: rename only changed the canonical's spelling, so it has no absorbed entity. They share one table
#: because the undo, the trail and the screen are the same for both, and a second ledger would be a
#: second definition of "put the name back" (AGENTS.md IV). The column's check constraint accepts
#: exactly these two values.
KIND_MERGE = "MERGE"
KIND_RENAME = "RENAME"


@dataclass(frozen=True)
class EntityRenameRecord:
    """
    What one rename changed, captured **before** the write so the ledger can reverse it without loss.

    A frozen dataclass and not a Pydantic model: it is computed inside the domain and only handed
    around (the ``api`` rule file's split), and it never crosses the HTTP boundary.

    ``synonym_created`` answers "did this rename plant the old spelling?", which is what the undo has
    to know: it deletes the spelling it planted and moves back the one that already existed.
    ``synonym_previous_entity_id`` is the target that pre-existed, recorded even when the caller asked
    for no synonym at all — then the state is the one the undo must leave alone, and pointing the
    spelling back to where it already points is exactly that.
    """

    entity_id: int
    entity_type: str
    previous_name: str
    new_name: str
    synonym_created: bool
    synonym_previous_entity_id: int | None
