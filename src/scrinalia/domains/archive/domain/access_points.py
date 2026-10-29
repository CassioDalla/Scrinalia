"""
The one reading of a raw "indexing points" string.

The manual form, the CSV import and the scraper all store the same shape: a string of access points
separated by comma, semicolon or pipe. The transfer turns it into tags through
``TagService.extract_and_clean_tags``; the creation form previews the same reading through
``TagService.preview_access_points``. Both call this module, so the rules cannot drift.

An ``AccessPointCandidate`` is a frozen dataclass: it is computed internally and handed around,
never parsed from a payload or serialized into the contract.
"""

from __future__ import annotations

import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from enum import StrEnum


class AccessPointStatus(StrEnum):
    """
    What the transfer will do with one access point of the raw string.

    ``EXISTING`` and ``SYNONYM`` link a tag that is already in the catalogue; ``NEW`` is a spelling
    the transfer will create; the other four are entries it will drop, each for a different reason.
    """

    EXISTING = "EXISTING"
    SYNONYM = "SYNONYM"
    NEW = "NEW"
    STOPWORD = "STOPWORD"
    TOO_SHORT = "TOO_SHORT"
    TOO_LONG = "TOO_LONG"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True, slots=True)
class AccessPointCandidate:
    """One entry of the raw string, with the reason the transfer would drop it (or ``None``)."""

    input: str
    normalized: str
    dropped: AccessPointStatus | None


#: The separators the pipeline accepts. The staging validator rewrites ``;`` to ``,`` before the
#: transfer reads the string; the form and the preview see the raw text, so the split has to accept
#: it here as well or a pasted list would be read as a single tag. ``|`` is the delimiter a source
#: key can carry, and the old extraction already split on it.
SEPARATORS = re.compile(r"[,|;]")

#: The same limits the extraction has always applied: one and two characters are noise, and the
#: column is 100 characters wide.
MIN_LENGTH = 3
MAX_LENGTH = 100


def classify_indexing_points(indexing_points: str | None, stopwords: AbstractSet[str]) -> list[AccessPointCandidate]:
    """
    Reads the raw string into candidates, marking what the transfer would drop.

    The order is preserved — the first spelling of a duplicate wins — and the whitespace is
    collapsed **before** the stopword check: a ban on ``rio branco`` has to catch ``rio  branco``,
    which the previous order let through to become a tag.
    """
    if not indexing_points:
        return []

    seen: set[str] = set()
    candidates: list[AccessPointCandidate] = []

    for raw in SEPARATORS.split(indexing_points):
        text = raw.strip()
        if not text:
            continue

        normalized = re.sub(r"\s+", " ", text.lower())
        dropped: AccessPointStatus | None = None

        if normalized in stopwords:
            dropped = AccessPointStatus.STOPWORD
        elif len(normalized) < MIN_LENGTH:
            dropped = AccessPointStatus.TOO_SHORT
        elif len(normalized) > MAX_LENGTH:
            dropped = AccessPointStatus.TOO_LONG
        elif normalized in seen:
            dropped = AccessPointStatus.DUPLICATE
        else:
            seen.add(normalized)

        candidates.append(AccessPointCandidate(input=text, normalized=normalized, dropped=dropped))

    return candidates
