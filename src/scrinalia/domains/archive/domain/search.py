"""
Query-side helpers for the collection search.

Kept free of SQLAlchemy so the tokenization rules can be unit tested without a
database. The repository composes these tokens into both the PostgreSQL ``tsquery``
and the taxonomy ``ILIKE`` predicates, so a term is interpreted the same way
everywhere it is used.
"""

import re

# Word characters only: keeps accents and digits, drops every character that could
# inject a ``tsquery`` operator (``&``, ``|``, ``!``, ``:``, ``*``, quotes).
_TOKEN_PATTERN = re.compile(r"[^\W_]+")


def tokenize(term: str) -> list[str]:
    """Splits a user term into safe search tokens, preserving accents."""
    return _TOKEN_PATTERN.findall(term)


def build_tsquery(tokens: list[str]) -> str | None:
    """
    Builds the string handed to PostgreSQL's ``to_tsquery``.

    Every token is required (AND) and the last one is prefix-expanded, so a term
    still being typed ("matad") keeps matching while the user types. ``to_tsquery``
    stems each token with the same dictionary that built the stored vector, so the
    prefix applies to the normalized lexeme rather than to the raw spelling.

    Returns ``None`` when there is nothing searchable (punctuation only), so the
    caller can skip the full-text clause instead of sending an empty query.
    """
    if not tokens:
        return None
    return " & ".join([*tokens[:-1], f"{tokens[-1]}:*"])
