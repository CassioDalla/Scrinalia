"""
The stable half of a route's answer: a code the client can translate, next to the sentence.

Every write route used to answer only ``message``, with the prose written in Portuguese inside the
controller. That is fine until the front has to speak another language: translating the screens
would leave every confirmation and every refusal in the server's language, and turning the prose
into an identifier later is an incompatible change (``message`` would stop being the text the
screen prints).

So a route answers both. ``code`` is the identity of the outcome — stable, English, and safe to
branch on or to look up in a translation catalogue. ``message`` stays the sentence, in Portuguese,
so a client that knows nothing about codes keeps working and a code with no translation yet still
has something to show.

Two rules for anyone adding a route:

* the code describes the **outcome**, not the wording, and never changes once released;
* a new code is an additive change to the enum, so an old client that does not know it falls back
  to ``message`` instead of rendering an empty string.

Do not put a ``Field(description=...)`` on a ``code`` field. Litestar applies the field's kwargs to
the **shared** enum component, so the description would not document the field — it would become
the enum's description for the whole document, and which field wins depends on the walk order (and
therefore on ``PYTHONHASHSEED``). Document the type here; the docstring reaches the contract.
"""

import enum

from pydantic import BaseModel


class RouteMessageCode(enum.StrEnum):
    """
    What a write route did, as an identifier rather than a sentence.

    One member per outcome, shared by the routes that can produce it: creating and deactivating a
    cleaning rule answer the same schema with different codes, because the screen says different
    things and a translation catalogue needs to tell them apart.
    """

    # --- Cleaning rules (data quality) ---
    CLEANING_RULE_CREATED = "CLEANING_RULE_CREATED"
    CLEANING_RULE_DEACTIVATED = "CLEANING_RULE_DEACTIVATED"

    # --- Text excerpts (the boilerplate the AI must not read) ---
    TEXT_TEMPLATE_SUGGESTED = "TEXT_TEMPLATE_SUGGESTED"
    TEXT_TEMPLATE_CREATED = "TEXT_TEMPLATE_CREATED"
    TEXT_TEMPLATE_UPDATED = "TEXT_TEMPLATE_UPDATED"
    TEXT_TEMPLATE_DELETED = "TEXT_TEMPLATE_DELETED"

    # --- The description itself ---
    DOCUMENT_DELETED = "DOCUMENT_DELETED"

    # --- The subject axis (tags and drawers) ---
    TAG_MERGE_PROPOSAL_DECIDED = "TAG_MERGE_PROPOSAL_DECIDED"
    TAG_MERGE_UNDONE = "TAG_MERGE_UNDONE"
    TAG_STOPWORDS_BANNED = "TAG_STOPWORDS_BANNED"
    TAG_STOPWORDS_REMOVED = "TAG_STOPWORDS_REMOVED"
    TAG_STOPWORD_PURGE_DONE = "TAG_STOPWORD_PURGE_DONE"
    SUBJECT_EXCLUSIONS_ADDED = "SUBJECT_EXCLUSIONS_ADDED"
    SUBJECT_EXCLUSIONS_REMOVED = "SUBJECT_EXCLUSIONS_REMOVED"
    MACRO_CLUSTERING_INSUFFICIENT_TEXTS = "MACRO_CLUSTERING_INSUFFICIENT_TEXTS"

    # --- The named entities (NER) ---
    NER_EXCLUSIONS_ADDED = "NER_EXCLUSIONS_ADDED"
    NER_EXCLUSIONS_REMOVED = "NER_EXCLUSIONS_REMOVED"
    ORPHAN_ENTITIES_PURGED = "ORPHAN_ENTITIES_PURGED"
    ENTITY_RECLASSIFIED = "ENTITY_RECLASSIFIED"
    ENTITY_DELETED = "ENTITY_DELETED"

    # --- The tag x entity collision ---
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"


class RouteResponse(BaseModel):
    """
    Base of every route answer that carries a human sentence.

    Kept as a base class rather than a field repeated in nineteen schemas: one definition means one
    place to change, and a test can assert that no message-bearing response was left without a code.
    """

    code: RouteMessageCode
    message: str


__all__ = ["RouteMessageCode", "RouteResponse"]
