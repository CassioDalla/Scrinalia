"""The one definition of every state a tag's subject can be in.

Two reads ask these questions and they must never disagree: the counters of the curator's home
(``CurationRepository.count_pending``) and the filter of the tag catalogue
(``TagRepository.list_catalog``). A card that promises 76 orphan tags next to a list whose first
page does not contain them is the read lying about the work — so the predicates live here, are
imported by both repositories, and ``testing/integration/api/controller/test_tag_catalog.py`` pins
that the card's number is the list's ``total``.

The decision has three parts and they are a **partition**, and each part has one durable marker:

* **pending** — no drawer and no verdict. ``macro_category_id IS NULL`` alone is *not* this:
  ``NULL`` is also what the human verdict writes, which is why a count built on the column alone
  can never reach zero.
* **not a subject** — the verdict, and the durable half of it is ``domain_subject_exclusions``,
  the table ``worker_macro_category`` actually obeys (``is_subject_candidate`` says nothing about
  the curated terms). Worse than cosmetic: a tag the human emptied comes back to the classifier
  each time the label set changes and gets a drawer again, so a verdict that is only stored in
  ``macro_category_id`` is a verdict the next run overwrites. Since ADR 0013 the same write also
  bans the spelling at ``TAG`` scope, so the next ingestion does not recreate the term.
* **a drawer** — ``macro_category_id`` pointing at the catalogue. It is reached with
  ``macro_category_id`` and not with a state; the two states above are the ones a catalogue filter
  names.

A place, a producer or a person is not a state of the tag: the entity axis carries *what it is*, with
a type search and diffusion consume, and the tag x entity conflict resolution is what settles a
spelling that is both. ``archive_tag_facets`` used to be a third state here and is gone (ADR 0013) —
its only reader was the chip this partition feeds.

The write path keeps the partition by writing the **whole** state at once
(``TagService.curate_tag_macro_category``): choosing one destination clears the other. The exclusion
write cannot create the collision from its side either: it refuses a term whose tag is in a drawer, so
no row is "in a category" and "out of the subject axis" at the same time. What each state *means* is
decided here, in one place; what the writes do about it is composed there.
"""

from sqlalchemy import ColumnElement, and_, exists, func, not_, select

from scrinalia.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveReviewStatus,
    ArchiveTag,
    DomainSubjectExclusion,
    TagCatalogState,
)

#: ``archive_tags.name`` is not stored normalized — the unique index is on ``lower(btrim(name))`` —
#: so the exclusion, which stores ``normalize_tag``, has to be matched through the same expression.
_NORMALIZED_NAME = func.lower(func.btrim(ArchiveTag.name))


def subject_not_subject() -> ColumnElement[bool]:
    """A person declared this tag belongs to no subject drawer."""
    return exists(select(1).select_from(DomainSubjectExclusion).where(DomainSubjectExclusion.term == _NORMALIZED_NAME))


def subject_pending() -> ColumnElement[bool]:
    """Nobody has decided this tag's subject: no drawer and no verdict."""
    return and_(
        ArchiveTag.macro_category_id.is_(None),
        not_(subject_not_subject()),
    )


def subject_low_confidence() -> ColumnElement[bool]:
    """
    Queued by the classifier below its confidence floor, and still undecided.

    The ``PENDING`` half is not redundant: the queue row is the classifier's *evidence*, and nothing
    deletes it when a human decides. Reading the row alone would leave the card counting a tag whose
    drawer the archivist already chose — the "work" would outlive the decision — so the state is the
    row **and** the absence of a verdict.
    """
    return and_(
        subject_pending(),
        exists(
            select(1)
            .select_from(ArchiveAIReviewQueue)
            .where(
                ArchiveAIReviewQueue.anomaly_type == AnomalyType.SUBJECT_LOW_CONFIDENCE,
                ArchiveAIReviewQueue.status == ArchiveReviewStatus.NEEDS_REVIEW,
                # The tag id is in the payload because the row has no foreign key: the queue is a
                # snapshot of the evidence, like the merge proposals' member list. Same cast the
                # conflict reads use (``entity_repo``).
                ArchiveAIReviewQueue.context_payload["tag_id"].as_integer() == ArchiveTag.tag_id,
            )
        ),
    )


def subject_state_condition(state: TagCatalogState, macro_category_id: int | None = None) -> ColumnElement[bool] | None:
    """
    The predicate behind one catalogue filter; ``None`` means "every tag".

    A drawer filter and a state are different questions and the caller may ask both: the screen
    offers the three states as chips and a category as a select, and "in this drawer" is answered by
    the column while the state answers "decided how".
    """
    conditions: list[ColumnElement[bool]] = []
    if state is TagCatalogState.PENDING:
        conditions.append(subject_pending())
    elif state is TagCatalogState.NOT_SUBJECT:
        # No drawer as well as the verdict: the column is ``NULL`` for a tag nobody decided about and
        # for one the archivist emptied, and only the second is this state.
        conditions.append(and_(ArchiveTag.macro_category_id.is_(None), subject_not_subject()))
    elif state is TagCatalogState.LOW_CONFIDENCE:
        conditions.append(subject_low_confidence())

    if macro_category_id is not None:
        conditions.append(ArchiveTag.macro_category_id == macro_category_id)

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return and_(*conditions)
