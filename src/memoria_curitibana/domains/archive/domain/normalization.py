"""
Canonical normalization rules for taxonomy and entity names.

These functions are the single definition of how a raw label becomes a stored
key in the Archive layer. Keeping them pure makes the rule explicit and testable,
instead of the ``.strip().lower()`` call being repeated (and drifting) across
services, repositories and workers.
"""


def normalize_tag(name: str) -> str:
    """Canonical form of a tag / subject key (lowercase, trimmed)."""
    return name.strip().lower()


def normalize_entity(name: str) -> str:
    """Canonical form of an entity name (lowercase, trimmed)."""
    return name.strip().lower()


def normalize_synonym(name: str) -> str:
    """Canonical form of a synonym key, matching the storage rule."""
    return name.strip().lower()


def normalize_stopword(word: str) -> str:
    """Canonical form of a stopword (lowercase, trimmed)."""
    return word.strip().lower()


def is_blank(name: str) -> bool:
    """True when the label has no meaningful content."""
    return not name or not name.strip()
