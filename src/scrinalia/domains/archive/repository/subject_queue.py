"""The one definition of every state a tag's subject can be in.

Two reads ask these questions and they must never disagree: the counters of the curator's home
(``CurationRepository.count_pending``) and the filter of the tag catalogue
(``TagRepository.list_catalog``). A card that promises 76 orphan tags next to a list whose first
page does not contain them is the read lying about the work — so the predicates live here, are
imported by both repositories, and ``testing/integration/api/controller/test_tag_catalog.py`` pins
that the card's number is the list's ``total``.

The decision has four parts and they are a **partition**, and each part has one durable marker:

* **pending** — no drawer, no verdict, no facet. ``macro_category_id IS NULL`` alone is *not* this:
  ``NULL`` is also what the human verdict writes, which is why a count built on the column alone
  can never reach zero.
* **not a subject** — the verdict, and the durable half of it is ``domain_subject_exclusions``,
  the table ``worker_macro_category`` actually obeys (``is_subject_candidate`` says nothing about
  the curated terms). Worse than cosmetic: a tag the human emptied comes back to the classifier
  each time the label set changes and gets a drawer again, so a verdict that is only stored in
  ``macro_category_id`` is a verdict the next run overwrites.
* **facet** — ``archive_tag_facets``: a producer or a place, which is a *positive* statement about
  the non-subject axis. A tag on that axis is also excluded from the subject axis, because the
  classifier must not file it either.
* **a drawer** — ``macro_category_id`` pointing at the catalogue. It is reached with
  ``macro_category_id`` and not with a state; the three states above are the ones a catalogue filter
  names.

The write path keeps the partition by writing the **whole** state at once
(``TagService.curate_tag_macro_category`` and ``TagService.declare_tag_facet``): choosing one
destination clears the others. What each state *means* is decided here, in one place; what the
writes do about it is composed there.
"""

from sqlalchemy import ColumnElement, and_, exists, func, not_, select

from scrinalia.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveReviewStatus,
    ArchiveTag,
    ArchiveTagFacet,
    DomainSubjectExclusion,
    TagCatalogState,
)

#: ``archive_tags.name`` is not stored normalized — the unique index is on ``lower(btrim(name))`` —
#: so the exclusion, which stores ``normalize_tag``, has to be matched through the same expression.
_NORMALIZED_NAME = func.lower(func.btrim(ArchiveTag.name))


def subject_not_subject() -> ColumnElement[bool]:
    """A person declared this tag belongs to no subject drawer."""
    return exists(select(1).select_from(DomainSubjectExclusion).where(DomainSubjectExclusion.term == _NORMALIZED_NAME))


def subject_is_facet() -> ColumnElement[bool]:
    """The tag is claimed by the non-subject axis: a producer or a place."""
    return exists(select(1).select_from(ArchiveTagFacet).where(ArchiveTagFacet.tag_id == ArchiveTag.tag_id))


def subject_pending() -> ColumnElement[bool]:
    """Nobody has decided this tag's subject: no drawer, no verdict, no facet."""
    return and_(
        ArchiveTag.macro_category_id.is_(None),
        not_(subject_not_subject()),
        not_(subject_is_facet()),
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
    offers the four states as chips and a category as a select, and "in this drawer" is answered by
    the column while the state answers "decided how".
    """
    conditions: list[ColumnElement[bool]] = []
    if state is TagCatalogState.PENDING:
        conditions.append(subject_pending())
    elif state is TagCatalogState.NOT_SUBJECT:
        # "Goes nowhere", which is a different statement from "goes to the non-subject axis": a
        # facet tag is excluded from the subject axis too, and the two must not both claim it.
        conditions.append(and_(ArchiveTag.macro_category_id.is_(None), subject_not_subject(), not_(subject_is_facet())))
    elif state is TagCatalogState.FACET:
        conditions.append(subject_is_facet())
    elif state is TagCatalogState.LOW_CONFIDENCE:
        conditions.append(subject_low_confidence())

    if macro_category_id is not None:
        conditions.append(ArchiveTag.macro_category_id == macro_category_id)

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return and_(*conditions)
