"""The sentences a route answers, in the request's language (ADR 0020 §4).

The Portuguese stays at the call site as the fallback and the English lives here, keyed by the stable
code: one definition per language, and a call site that forgets a code still answers in Portuguese
rather than failing a write that already happened.
"""

from __future__ import annotations

from scrinalia.core.i18n import current_locale
from scrinalia.core.locale import Locale
from scrinalia.domains.archive.schemas.responses import RouteMessageCode

#: The English sentence of every route outcome. The Portuguese stays at the call site as the
#: fallback, so there is one definition per language and a code added here without a call site is
#: harmless. ``route_message`` renders the English only when the request asks for it.
ROUTE_MESSAGES_EN: dict[RouteMessageCode, str] = {
    RouteMessageCode.CLEANING_RULE_CREATED: "Rule saved and activated. The worker will start the sweep.",
    RouteMessageCode.CLEANING_RULE_DEACTIVATED: "Rule deactivated.",
    RouteMessageCode.CLEANING_RULE_ACTIVATED: "Rule reactivated.",
    RouteMessageCode.TEXT_TEMPLATE_SUGGESTED: (
        "{candidates} repeated excerpt(s) found in {documents} document(s). Nothing was applied: "
        "approve, edit or reject each candidate."
    ),
    RouteMessageCode.TEXT_TEMPLATE_CREATED: (
        "Excerpt registered and applied. The affected documents returned to the AI queue."
    ),
    RouteMessageCode.TEXT_TEMPLATE_UPDATED: "Excerpt updated. The affected documents returned to the AI queue.",
    RouteMessageCode.TEXT_TEMPLATE_DELETED: (
        "Excerpt removed from the catalogue and its effect undone on the affected documents."
    ),
    RouteMessageCode.DOCUMENT_DELETED: "Description '{title}' deleted from the collection.",
    RouteMessageCode.MANUAL_INGESTION_QUEUED: (
        "Description received and structured. The transfer was queued; the AI will enrich it and the "
        "record stays in review."
    ),
    RouteMessageCode.MANUAL_INGESTION_STAGED: (
        "Description received and structured. A transfer is already in progress, so it enters the next one "
        "and goes to the AI afterwards."
    ),
    RouteMessageCode.CSV_IMPORT_QUEUED: (
        "{accepted} of {received} rows imported ({duplicated} duplicated, {invalid} invalid). The transfer "
        "was queued; the AI will enrich them and they stay in review."
    ),
    RouteMessageCode.CSV_IMPORT_STAGED: (
        "{accepted} of {received} rows imported ({duplicated} duplicated, {invalid} invalid). A transfer is "
        "already in progress, so they enter the next one and go to the AI afterwards."
    ),
    RouteMessageCode.CSV_IMPORT_REFUSED: (
        "None of the {received} rows entered: {duplicated} duplicated and {invalid} invalid. Fix the preview "
        "and send again."
    ),
    RouteMessageCode.WORKER_RUN_CANCELLED: "Run cancelled: it had not been claimed by a runner yet.",
    RouteMessageCode.WORKER_RUN_CANCEL_REQUESTED: (
        "Cancellation requested: the run stops at the end of the current batch."
    ),
    RouteMessageCode.WORKER_RUN_CANCEL_ALREADY_REQUESTED: (
        "This run's cancellation had already been requested; it stops at the end of the current batch."
    ),
    RouteMessageCode.TAG_MERGE_PROPOSAL_DECIDED: ("Decision recorded. The merge is only applied when the batch runs."),
    RouteMessageCode.TAG_MERGE_UNDONE: "Merge undone: the tag '{absorbed_name}' was restored.",
    RouteMessageCode.TAG_STOPWORDS_BANNED: "{created} stopword(s) registered on the {scope} axis.",
    RouteMessageCode.TAG_STOPWORDS_MATCH_UPDATED: "{updated} stopword(s) now match by {match_mode}.",
    RouteMessageCode.TAG_STOPWORDS_REMOVED: "{removed} stopword(s) removed.",
    RouteMessageCode.TAG_STOPWORD_PURGE_DONE: "Purge completed.",
    RouteMessageCode.TAG_STOPWORD_PURGE_UNDONE: "Purge undone: the tag '{purged_name}' was restored.",
    RouteMessageCode.SUBJECT_EXCLUSIONS_ADDED: (
        "Terms marked as not-a-subject: the subject classifier will ignore them and the spellings will not "
        "become tags again."
    ),
    RouteMessageCode.SUBJECT_EXCLUSIONS_BLOCKED: (
        "No term was marked: the tags below are already in a subject category. Remove them from the category "
        "in the tag catalogue before declaring them not-a-subject."
    ),
    RouteMessageCode.SUBJECT_EXCLUSIONS_PARTIAL: (
        "{created} term(s) marked as not-a-subject and banned from returning; {blocked} refused for already "
        "being in a subject category."
    ),
    RouteMessageCode.SUBJECT_EXCLUSIONS_REMOVED: "Exclusions removed: the classifier will consider these terms again.",
    RouteMessageCode.MACRO_CLUSTERING_INSUFFICIENT_TEXTS: "⚠️ Not enough text to form semantic groups.",
    RouteMessageCode.NER_EXCLUSIONS_ADDED: (
        "Terms marked as subject: the extractor will no longer treat them as entities."
    ),
    RouteMessageCode.NER_EXCLUSIONS_REMOVED: (
        "Exclusions removed: the extractor will consider these terms again. Entities already purged return "
        "through the purge undo, not here."
    ),
    RouteMessageCode.NER_PURGE_DONE: (
        "Purge completed: the entities already extracted were removed and can be restored."
    ),
    RouteMessageCode.NER_PURGE_UNDONE: "Purge undone: the entity '{purged_name}' was restored.",
    RouteMessageCode.ORPHAN_ENTITIES_PURGED: "Orphan entity cleanup completed.",
    RouteMessageCode.ENTITY_RECLASSIFIED: "Entity reclassified and an anchoring synonym generated.",
    RouteMessageCode.ENTITY_RENAMED: "Entity renamed.",
    RouteMessageCode.ENTITY_DELETED: "Entity {entity_id} deleted from the database.",
    RouteMessageCode.ENTITY_MERGE_UNDONE: "Merge undone: the entity '{absorbed_name}' was restored.",
    RouteMessageCode.CONFLICT_RESOLVED: (
        "Conflict resolved in favour of {winner}: {documents_transferred} link(s) transferred. The resolution can be "
        "undone."
    ),
    RouteMessageCode.CONFLICT_BATCH_RESOLVED: (
        "{applied} collision(s) resolved in favour of {winner} in a batch; {remaining} remain in the "
        "selection; {skipped} had nothing left to resolve; {failed} failed."
    ),
    RouteMessageCode.SESSION_ENDED: "Signed out.",
    RouteMessageCode.PASSWORD_CHANGED: "Password changed. The account's other sessions were ended.",
    RouteMessageCode.PASSWORD_CHANGE_REQUIRED: "Change the temporary password before using the system.",
    RouteMessageCode.USER_PASSWORD_RESET: "Password reset. This account's sessions were ended.",
    RouteMessageCode.USER_SESSIONS_REVOKED: "{ended} session(s) ended.",
    RouteMessageCode.SESSION_REVOKED: "Session ended.",
}


def route_message(code: RouteMessageCode, fallback: str, **facts: object) -> str:
    """
    The sentence for a route answer in the request's language.

    The Portuguese text stays at the call site as the fallback; the English is the catalogue entry.
    A code with no English entry answers in Portuguese rather than failing the write: the outcome
    already happened, and an untranslated sentence is better than a 500.
    """
    template = ROUTE_MESSAGES_EN.get(code) if current_locale() is Locale.EN else None
    return (template or fallback).format(**facts)
