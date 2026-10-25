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
    CLEANING_RULE_ACTIVATED = "CLEANING_RULE_ACTIVATED"

    # --- Text excerpts (the boilerplate the AI must not read) ---
    TEXT_TEMPLATE_SUGGESTED = "TEXT_TEMPLATE_SUGGESTED"
    TEXT_TEMPLATE_CREATED = "TEXT_TEMPLATE_CREATED"
    TEXT_TEMPLATE_UPDATED = "TEXT_TEMPLATE_UPDATED"
    TEXT_TEMPLATE_DELETED = "TEXT_TEMPLATE_DELETED"

    # --- The description itself ---
    DOCUMENT_DELETED = "DOCUMENT_DELETED"

    # --- The operations panel (the run ledger) ---
    #: The ingestion origin received the record, staged it and queued the transfer run.
    MANUAL_INGESTION_QUEUED = "MANUAL_INGESTION_QUEUED"
    #: The record was staged, but a transfer was already in flight; it enters the next one.
    MANUAL_INGESTION_STAGED = "MANUAL_INGESTION_STAGED"
    #: At least one CSV row was written and staged, and the transfer was enqueued.
    CSV_IMPORT_QUEUED = "CSV_IMPORT_QUEUED"
    #: At least one CSV row was staged, but a transfer was already in flight.
    CSV_IMPORT_STAGED = "CSV_IMPORT_STAGED"
    #: No CSV row entered: every one was duplicated or invalid, and the report says which.
    CSV_IMPORT_REFUSED = "CSV_IMPORT_REFUSED"
    #: The run was still queued with no runner: it never started, so it closed at once.
    WORKER_RUN_CANCELLED = "WORKER_RUN_CANCELLED"
    #: The run is in flight: the request was recorded and the worker stops at the next batch
    #: boundary. The row stays ``QUEUED``/``RUNNING`` and keeps its slot until then.
    WORKER_RUN_CANCEL_REQUESTED = "WORKER_RUN_CANCEL_REQUESTED"

    # --- The subject axis (tags and drawers) ---
    TAG_MERGE_PROPOSAL_DECIDED = "TAG_MERGE_PROPOSAL_DECIDED"
    TAG_MERGE_UNDONE = "TAG_MERGE_UNDONE"
    TAG_STOPWORDS_BANNED = "TAG_STOPWORDS_BANNED"
    TAG_STOPWORDS_REMOVED = "TAG_STOPWORDS_REMOVED"
    TAG_STOPWORDS_MATCH_UPDATED = "TAG_STOPWORDS_MATCH_UPDATED"
    TAG_STOPWORD_PURGE_DONE = "TAG_STOPWORD_PURGE_DONE"
    TAG_STOPWORD_PURGE_UNDONE = "TAG_STOPWORD_PURGE_UNDONE"
    SUBJECT_EXCLUSIONS_ADDED = "SUBJECT_EXCLUSIONS_ADDED"
    #: The write refused every term because its tag sits in a subject drawer (issue #83, option C).
    SUBJECT_EXCLUSIONS_BLOCKED = "SUBJECT_EXCLUSIONS_BLOCKED"
    #: Some terms were recorded and some refused: the screen has to say both numbers.
    SUBJECT_EXCLUSIONS_PARTIAL = "SUBJECT_EXCLUSIONS_PARTIAL"
    SUBJECT_EXCLUSIONS_REMOVED = "SUBJECT_EXCLUSIONS_REMOVED"
    MACRO_CLUSTERING_INSUFFICIENT_TEXTS = "MACRO_CLUSTERING_INSUFFICIENT_TEXTS"

    # --- The named entities (NER) ---
    NER_EXCLUSIONS_ADDED = "NER_EXCLUSIONS_ADDED"
    NER_EXCLUSIONS_REMOVED = "NER_EXCLUSIONS_REMOVED"
    #: The destructive half of the NER veto: the entities already extracted from a banned spelling.
    NER_PURGE_DONE = "NER_PURGE_DONE"
    NER_PURGE_UNDONE = "NER_PURGE_UNDONE"
    ORPHAN_ENTITIES_PURGED = "ORPHAN_ENTITIES_PURGED"
    ENTITY_RECLASSIFIED = "ENTITY_RECLASSIFIED"
    ENTITY_DELETED = "ENTITY_DELETED"
    ENTITY_RENAMED = "ENTITY_RENAMED"
    ENTITY_MERGE_UNDONE = "ENTITY_MERGE_UNDONE"

    # --- The tag x entity collision ---
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    #: One categorical verdict written over a whole selection of pairs, one ledger row each.
    CONFLICT_BATCH_RESOLVED = "CONFLICT_BATCH_RESOLVED"

    # --- The session and the account (identity) ---
    # The codes of the identity routes live in the same enum because the enum is the shared
    # vocabulary of "what a write route did", and the front reads every one of them through the same
    # seam. The cross-domain import it implies is in the API layer, which is the composition point
    # and already speaks both domains; the identity domain itself imports nothing from the archive.
    SESSION_ENDED = "SESSION_ENDED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    #: The account still carries the temporary password the CLI generated (or an administrator
    #: typed), so the guard refuses every operation but the change itself and the ways out the
    #: forced screen needs. An outcome and not a wording: it names the refusal, not the sentence.
    PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"
    #: An administrator replaced somebody's password, which ended every session of that account.
    USER_PASSWORD_RESET = "USER_PASSWORD_RESET"
    #: Every session of one account was ended at once.
    USER_SESSIONS_REVOKED = "USER_SESSIONS_REVOKED"
    #: One session of one account was ended.
    SESSION_REVOKED = "SESSION_REVOKED"


class RouteResponse(BaseModel):
    """
    Base of every route answer that carries a human sentence.

    Kept as a base class rather than a field repeated in nineteen schemas: one definition means one
    place to change, and a test can assert that no message-bearing response was left without a code.
    """

    code: RouteMessageCode
    message: str


__all__ = ["RouteMessageCode", "RouteResponse"]
