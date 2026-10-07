"""
Pure rules of the tag-merge proposals.

What the suggester computes (which tags look like the same concept) is evidence; what a
human decides about that evidence is a curation act. This module owns the vocabulary the
two sides share — how a proposal is identified, which lifecycle states it can be in and
which warnings the curator must look at before approving — so the repository, the service
and the HTTP contract cannot drift from each other.
"""

import hashlib
import re
from collections.abc import Sequence

from scrinalia.domains.archive.domain.normalization import normalize_tag

#: How the cluster was formed: spelling closeness (``TRIGRAM``), the singular/plural rule
#: (``PLURAL``) or both (``MIXED``). Stored as a string with a CHECK, like the other
#: catalogs of this layer, so a new piece of evidence does not need a schema migration.
MERGE_REASONS = ("TRIGRAM", "PLURAL", "MIXED")

#: Curation lifecycle of a proposal. The routine only ever writes ``SUGGESTED``; a human
#: moves it to ``APPROVED``/``REJECTED`` and a re-run never overwrites that decision.
PROPOSAL_STATUSES = ("SUGGESTED", "APPROVED", "REJECTED")

#: The member carries a number. Measured on the real collection, this is where the wrong
#: proposals concentrate (``rua 24 de maio`` <- ``rua 13 de maio``, ``303 anos`` <-
#: ``anos 30``): near-identical spellings, different subjects. The flag asks for a human
#: look — it never rejects anything on its own.
REVIEW_MEMBER_WITH_DIGITS = "MEMBER_WITH_DIGITS"

#: The member is similar to another member but not directly to the canonical, so its link
#: to the cluster is indirect. Measured: 3 of 466 absorbed tags, i.e. rare.
REVIEW_WEAK_MEMBER = "WEAK_MEMBER"

#: The canonical has no macro category while an absorbed member does. The merge would drop
#: that classification unless the curator says otherwise, so the dry-run reports it.
REVIEW_CATEGORY_WOULD_BE_LOST = "CATEGORY_WOULD_BE_LOST"

#: The absorbed spelling is already a synonym of another tag, so two decisions would
#: compete over it.
REVIEW_MEMBER_IS_SYNONYM = "MEMBER_IS_SYNONYM"

#: ``pg_trgm`` similarity below this marks the indirect link described above.
WEAK_MEMBER_SIMILARITY = 0.4

_DIGITS = re.compile(r"\d")


def cluster_fingerprint(canonical_name: str, member_names: Sequence[str]) -> str:
    """
    Stable identity of a proposal, which is what makes the suggestion routine idempotent.

    Built from the **spellings**, not the ids: ids are reassigned when a tag is deleted and
    recreated, while the cluster is a statement about names. The member list is sorted, so
    the order the union-find happened to produce does not create a second proposal for the
    same set.
    """
    names = sorted(normalize_tag(name) for name in member_names)
    payload = "\x1f".join([normalize_tag(canonical_name), *names])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def has_digits(name: str) -> bool:
    """True when the spelling carries a number (see ``REVIEW_MEMBER_WITH_DIGITS``)."""
    return bool(_DIGITS.search(name))
