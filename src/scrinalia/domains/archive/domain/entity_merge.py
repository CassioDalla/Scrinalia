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
