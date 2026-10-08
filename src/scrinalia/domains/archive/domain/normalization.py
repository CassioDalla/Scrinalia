"""
Canonical normalization rules for taxonomy and entity names.

These functions are the single definition of how a raw label becomes a stored
key in the Archive layer. Keeping them pure makes the rule explicit and testable,
instead of the ``.strip().lower()`` call being repeated (and drifting) across
services, repositories and workers.
"""

from scrinalia.core.language import get_language


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


#: Escape character declared to PostgreSQL in every ``ILIKE ... ESCAPE`` we emit. Kept a constant
#: so the escaping function and the queries cannot disagree about the literal.
LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """
    Neutralises the wildcards in a term a person typed, so that a search is a search.

    Without it, a ``%`` in the search box matches every row and an ``_`` matches any character:
    the collection answers the whole catalogue to a typo, which reads as a broken ranking and
    costs a sequential scan. The escape character goes first, or it would escape the escapes.
    """
    escaped = term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
    return escaped.replace("%", f"{LIKE_ESCAPE}%").replace("_", f"{LIKE_ESCAPE}_")


def singular_candidates(name: str) -> list[str]:
    """
    Possible singular forms of a tag, for a **suggestion** of merging.

    The endings are a property of the language and come from the active profile
    (:mod:`scrinalia.core.language.pt_br`); the folding below is the rule and is language-neutral.

    Measured on the collection: 746 tags end in "s" and 130 of them have a naive
    singular that is also a tag ("livros"/"livro", "edifícios"/"edifício"). Lemmatizing
    at ingestion was rejected — it would change the identity of every new tag and risks
    inventing forms ("ônibus" has no singular). Here nothing is decided: the pairs are
    proposed and the archivist approves, exactly like the other curation flows.
    """
    candidates: list[str] = []
    for ending, replacement in get_language().plural_rules:
        if name.endswith(ending) and len(name) > len(ending):
            candidates.append(name[: -len(ending)] + replacement)
    return list(dict.fromkeys(candidates))
