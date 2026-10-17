"""
Query-side helpers for the collection search.

Kept free of SQLAlchemy so the tokenization rules and the fusion can be unit tested
without a database. The repository composes these tokens into both the PostgreSQL
``tsquery`` and the taxonomy ``ILIKE`` predicates, so a term is interpreted the same way
everywhere it is used.
"""

import re
from collections.abc import Sequence

# Word characters only: keeps accents and digits, drops every character that could
# inject a ``tsquery`` operator (``&``, ``|``, ``!``, ``:``, ``*``, quotes).
_TOKEN_PATTERN = re.compile(r"[^\W_]+")

#: The dampening constant of Reciprocal Rank Fusion (Cormack, Clarke and Buettcher, 2009).
#: It flattens what a single first position is worth, which is the point of the fusion: a
#: document both rankings found at position 20 must outrank one a single ranking put first.
RRF_K = 60

#: How many documents each ranking contributes to the fusion, and therefore the depth of the
#: window the fused order covers. Past it the page falls back to the lexical order, because
#: out there no ranking exists to fuse.
RRF_DEPTH = 100


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


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """
    Fuses ranked id lists into one ranking, by Reciprocal Rank Fusion.

    Each ranking contributes ``1 / (k + rank)`` to every id it carries, so the score speaks
    about the **agreement between rankings** and not about the scale of any of them — which is
    what lets a ``ts_rank`` and a cosine similarity be combined without normalising either.

    Agreement is a pull and not a rule. An id both rankings carry at comparable positions
    outscores one either ranking carries alone (``1/61 + 1/63 = 0.032266`` against ``1/61 =
    0.016393``), but the arithmetic is not a dominance order: a first place plus a third barely
    beats a second place twice (``0.032266`` against ``0.032258``), because the reciprocal is
    convex. What the fusion buys is a document no single ranking would have put first.

    An id counts once per ranking, at the best position it appears in: a ranking is a ranking,
    and a repeated row must not buy a second vote. Ties break by ``description_id``, so two runs
    over the same input cannot disagree about the order.

    ``k`` must be non-negative; the default is the constant the method was published with. An
    empty input is an empty fusion and not an error: a ranking with no candidate contributes
    nothing, which is what lets one arm be empty and the other carry the result alone.
    """
    if k < 0:
        raise ValueError("The RRF dampening constant cannot be negative.")

    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for position, description_id in enumerate(ranking, start=1):
            if description_id in seen:
                continue
            seen.add(description_id)
            scores[description_id] = scores.get(description_id, 0.0) + 1.0 / (k + position)

    return sorted(scores.items(), key=lambda scored: (-scored[1], scored[0]))
