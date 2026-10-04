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


#: Regular Portuguese plural endings mapped to the singular they may come from. Applied
#: only as *candidates*: a candidate becomes a merge suggestion when the singular already
#: exists as a tag, so an irregular word simply never matches and no term is invented.
_PLURAL_RULES: tuple[tuple[str, str], ...] = (
    ("ões", "ão"),
    ("ães", "ão"),
    ("ais", "al"),
    ("éis", "el"),
    ("eis", "el"),
    ("óis", "ol"),
    ("ois", "ol"),
    ("is", "il"),
    ("ns", "m"),
    ("es", "e"),
    ("s", ""),
)


def singular_candidates(name: str) -> list[str]:
    """
    Possible singular forms of a tag, for a **suggestion** of merging.

    Measured on the collection: 746 tags end in "s" and 130 of them have a naive
    singular that is also a tag ("livros"/"livro", "edifícios"/"edifício"). Lemmatizing
    at ingestion was rejected — it would change the identity of every new tag and risks
    inventing forms ("ônibus" has no singular). Here nothing is decided: the pairs are
    proposed and the archivist approves, exactly like the other curation flows.
    """
    candidates: list[str] = []
    for ending, replacement in _PLURAL_RULES:
        if name.endswith(ending) and len(name) > len(ending):
            candidates.append(name[: -len(ending)] + replacement)
    return list(dict.fromkeys(candidates))
