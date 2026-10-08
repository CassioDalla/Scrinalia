"""
Integration tests of the tag x entity conflict: the preview has to equal the write, and the undo
has to be exact.

Three promises are pinned here, and each one was broken before this ledger existed:

* the **preview** describes what the apply does, because both read the same plan;
* the **write** is reversible — the losing row comes back with its id, its links come back, and the
  ban goes only if this resolution planted it;
* the **judge's verdict** is readable, including for the 84 auto-resolutions whose losing row was
  deleted and which the live trigram scan therefore cannot return.
"""

import pytest
from sqlalchemy import delete, select

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import (
    ConflictResolutionAlreadyUndoneError,
    ConflictResolutionNotFoundError,
    UnresolvableConflictError,
)
from scrinalia.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveDocumentEntity,
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveReviewStatus,
    ArchiveTag,
    DomainNerExclusion,
    DomainStopwords,
    StopwordsScope,
)
from scrinalia.domains.archive.repository.entity_repo import EntityRepository


def _link_tag(db_session, tag: ArchiveTag, document_id: str) -> None:
    db_session.add(ArchiveDocumentTag(description_id=document_id, tag_id=tag.tag_id))


def _link_entity(db_session, entity: ArchiveEntity, document_id: str) -> None:
    db_session.add(ArchiveDocumentEntity(description_id=document_id, entity_id=entity.entity_id))


def _pair(db_session, tag_name: str = "batel", entity_name: str = "Batel", entity_type: str = "LOC"):
    tag = ArchiveTag(name=tag_name)
    entity = ArchiveEntity(name=entity_name, entity_type=entity_type)
    db_session.add_all([tag, entity])
    db_session.flush()
    return tag, entity


def test_the_plan_counts_what_each_verdict_would_change(use_test_db, db_session, generate_archive_doc):
    """
    ``transferred`` counts the links the resolution would create; the overlap is counted apart.

    A document that already carries the winner is not touched by the resolution, so lumping it into
    "transferred" would overstate the impact and — worse — make the undo delete a link that predates
    it.
    """
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)

    already = generate_archive_doc(original_title="Já tem a tag e a entidade")
    only_entity = generate_archive_doc(original_title="Só a entidade")
    _link_tag(db_session, tag, already.description_id)
    _link_entity(db_session, entity, already.description_id)
    _link_entity(db_session, entity, only_entity.description_id)
    db_session.flush()

    plan = repo.plan_conflict_resolution(tag.tag_id, entity.entity_id)

    assert plan.resolvable is True
    assert plan.tag_alive and plan.entity_alive
    assert plan.tag_document_count == 1
    assert plan.entity_document_count == 2
    # TAG wins: one new link (the entity-only document), one that already existed.
    assert plan.tag_wins_documents_transferred == 1
    assert plan.tag_wins_documents_already_linked == 1
    assert plan.tag_wins_loses == "Batel"
    assert plan.tag_wins_ban_term == "Batel"
    assert plan.tag_wins_ban_exists is False
    # ENTITY wins: the tag's only document already carries the entity, so nothing new is linked.
    assert plan.entity_wins_documents_transferred == 0
    assert plan.entity_wins_documents_already_linked == 1
    assert plan.entity_wins_loses == "batel"

    # The plan writes nothing.
    assert db_session.scalar(select(ArchiveEntity).where(ArchiveEntity.entity_id == entity.entity_id)) is not None
    assert db_session.scalar(select(ArchiveTag).where(ArchiveTag.tag_id == tag.tag_id)) is not None


def test_the_preview_number_is_the_written_number(use_test_db, db_session, generate_archive_doc):
    """Plan and apply share one definition, so the dry run cannot promise something else."""
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    for index in range(3):
        doc = generate_archive_doc(original_title=f"Doc {index}")
        _link_entity(db_session, entity, doc.description_id)
    db_session.flush()

    plan = repo.plan_conflict_resolution(tag.tag_id, entity.entity_id)
    data = repo.apply_conflict_resolution(plan, "TAG", source="HUMAN", decided_by=Author(name="ana"))
    db_session.flush()

    assert data.documents_transferred == plan.tag_wins_documents_transferred == 3
    assert data.resolution_id is not None
    assert data.ban_kind == "NER_EXCLUSION"

    # The entity is gone and its documents now carry the tag.
    assert db_session.scalar(select(ArchiveEntity).where(ArchiveEntity.entity_id == entity.entity_id)) is None
    linked = db_session.scalars(
        select(ArchiveDocumentTag.description_id).where(ArchiveDocumentTag.tag_id == tag.tag_id)
    ).all()
    assert len(linked) == 3


def test_undo_restores_the_loser_its_id_and_only_the_links_it_created(use_test_db, db_session, generate_archive_doc):
    """
    The exact restore: the deleted row comes back with its id, and the links it brought with it.

    The document that already carried the tag before the resolution must keep a single link — the
    regression the merge ledger also guards against, where restoring the row without removing the
    created links leaves the document carrying both spellings.
    """
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    entity_id = entity.entity_id

    already = generate_archive_doc(original_title="Já tinha a tag")
    only_entity = generate_archive_doc(original_title="Só a entidade")
    _link_tag(db_session, tag, already.description_id)
    _link_entity(db_session, entity, already.description_id)
    _link_entity(db_session, entity, only_entity.description_id)
    db_session.flush()

    plan = repo.plan_conflict_resolution(tag.tag_id, entity.entity_id)
    data = repo.apply_conflict_resolution(plan, "TAG", source="HUMAN", decided_by=Author(name="ana"))
    db_session.flush()

    assert data.resolution_id is not None
    entry = repo.undo_conflict_resolution(data.resolution_id, undone_by=Author(name="bruno"))
    db_session.flush()

    assert entry.undone_by == "bruno"
    assert entry.loser_restored is True

    restored = db_session.get(ArchiveEntity, entity_id)
    assert restored is not None
    assert restored.name == "Batel"
    assert restored.entity_type == "LOC"

    # Both documents carried the entity before the resolution, so both come back with it.
    entity_links = set(
        db_session.scalars(
            select(ArchiveDocumentEntity.description_id).where(ArchiveDocumentEntity.entity_id == entity_id)
        ).all()
    )
    assert entity_links == {already.description_id, only_entity.description_id}

    # What the undo must remove is the link the resolution created: ``only_entity`` gained the tag,
    # and ``already`` had it before. Leaving it would leave the document with both spellings.
    tag_links = set(
        db_session.scalars(
            select(ArchiveDocumentTag.description_id).where(ArchiveDocumentTag.tag_id == tag.tag_id)
        ).all()
    )
    assert tag_links == {already.description_id}

    # The ban this resolution planted is lifted with it.
    assert db_session.scalar(select(DomainNerExclusion).where(DomainNerExclusion.term == "batel")) is None


def test_undo_does_not_lift_a_ban_it_did_not_plant(use_test_db, db_session, generate_archive_doc):
    """
    ``ban_created`` is what keeps one reversal from undoing an earlier decision.

    The ban is planted with ``ON CONFLICT DO NOTHING``, so a spelling already banned by a previous
    resolution must survive the reversal of a later one about the same spelling.
    """
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    doc = generate_archive_doc(original_title="Doc")
    _link_entity(db_session, entity, doc.description_id)
    # An earlier decision already banned the spelling.
    repo.add_ner_exclusions(["Batel"], source="HUMAN", reason="decisão anterior", tag_id=tag.tag_id)
    db_session.flush()

    plan = repo.plan_conflict_resolution(tag.tag_id, entity.entity_id)
    assert plan.tag_wins_ban_exists is True

    data = repo.apply_conflict_resolution(plan, "TAG", source="HUMAN")
    db_session.flush()
    assert data.resolution_id is not None
    repo.undo_conflict_resolution(data.resolution_id)
    db_session.flush()

    # The earlier ban is still there, and its author is still the earlier decision.
    ban = db_session.scalar(select(DomainNerExclusion).where(DomainNerExclusion.term == "batel"))
    assert ban is not None
    assert ban.reason == "decisão anterior"


def test_entity_winning_bans_the_tag_in_the_subject_axis(use_test_db, db_session, generate_archive_doc):
    """The other direction, and its own storage: the tag spelling joins the tag-scoped stopwords."""
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    doc = generate_archive_doc(original_title="Doc")
    _link_tag(db_session, tag, doc.description_id)
    db_session.flush()

    plan = repo.plan_conflict_resolution(tag.tag_id, entity.entity_id)
    data = repo.apply_conflict_resolution(plan, "ENTITY", source="HUMAN", decided_by=Author(name="ana"))
    db_session.flush()

    assert data.ban_kind == "STOPWORD"
    assert db_session.get(ArchiveTag, tag.tag_id) is None
    stopword = db_session.scalar(select(DomainStopwords).where(DomainStopwords.word == "batel"))
    assert stopword is not None
    assert stopword.word_scope == StopwordsScope.TAG

    # The entity kept the document.
    entity_links = db_session.scalars(
        select(ArchiveDocumentEntity.description_id).where(ArchiveDocumentEntity.entity_id == entity.entity_id)
    ).all()
    assert list(entity_links) == [doc.description_id]

    assert data.resolution_id is not None
    entry = repo.undo_conflict_resolution(data.resolution_id)
    db_session.flush()
    assert entry.loser_restored is True
    assert db_session.get(ArchiveTag, tag.tag_id) is not None
    assert db_session.scalar(select(DomainStopwords).where(DomainStopwords.word == "batel")) is None


def test_the_undo_is_single_shot_and_an_unknown_id_is_404(use_test_db, db_session, generate_archive_doc):
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    doc = generate_archive_doc(original_title="Doc")
    _link_entity(db_session, entity, doc.description_id)
    db_session.flush()

    data = repo.apply_conflict_resolution(repo.plan_conflict_resolution(tag.tag_id, entity.entity_id), "TAG")
    db_session.flush()
    assert data.resolution_id is not None
    repo.undo_conflict_resolution(data.resolution_id)
    db_session.flush()

    with pytest.raises(ConflictResolutionAlreadyUndoneError):
        assert data.resolution_id is not None
        repo.undo_conflict_resolution(data.resolution_id)

    with pytest.raises(ConflictResolutionNotFoundError):
        repo.undo_conflict_resolution(999999)


def test_a_pair_whose_loser_is_gone_is_not_resolvable(use_test_db, db_session):
    """The preview has to say the pair is dead instead of offering a button that answers 404."""
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    entity_id = entity.entity_id
    db_session.execute(delete(ArchiveEntity).where(ArchiveEntity.entity_id == entity_id))
    db_session.flush()

    plan = repo.plan_conflict_resolution(tag.tag_id, entity_id)

    assert plan.resolvable is False
    assert plan.entity_alive is False
    assert plan.blocker is not None
    with pytest.raises(UnresolvableConflictError):
        repo.apply_conflict_resolution(plan, "TAG")


def test_an_already_resolved_pair_says_so_in_the_preview(use_test_db, db_session, generate_archive_doc):
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    doc = generate_archive_doc(original_title="Doc")
    _link_entity(db_session, entity, doc.description_id)
    db_session.flush()

    repo.apply_conflict_resolution(repo.plan_conflict_resolution(tag.tag_id, entity.entity_id), "TAG")
    db_session.flush()

    plan = repo.plan_conflict_resolution(tag.tag_id, entity.entity_id)
    assert plan.already_resolved is True


# ==========================================
# THE READ THAT WAS MISSING: THE JUDGE'S VERDICTS
# ==========================================


def _judge_row(
    db_session,
    tag_id: int,
    tag_name: str,
    entity_id: int,
    entity_name: str,
    decision: str,
    status: ArchiveReviewStatus,
    confidence: float = 0.95,
) -> ArchiveAIReviewQueue:
    row = ArchiveAIReviewQueue(
        anomaly_type=AnomalyType.CROSS_DOMAIN_COLLISION,
        status=status,
        context_payload={
            "tag_id": tag_id,
            "tag_name": tag_name,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "entity_type": "LOC",
        },
        llm_decision=decision,
        llm_confidence=confidence,
        llm_reason="Regra 1 - Bairro é local palpável.",
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_the_judge_verdicts_are_readable_even_when_the_pair_is_gone(use_test_db, db_session):
    """
    The read that closes the gap: 84 of the 88 real decisions deleted the losing row.

    Reading the live trigram scan cannot return them — the pair no longer exists — so the queue is
    the only place the judge's work survives. ``tag_alive``/``entity_alive`` say which decisions are
    still about something.
    """
    repo = EntityRepository(db_session)

    # An auto-resolution: the entity was deleted by the judge, the queue row survives.
    dead_tag = ArchiveTag(name="terminal guadalupe")
    db_session.add(dead_tag)
    db_session.flush()
    _judge_row(
        db_session,
        dead_tag.tag_id,
        "terminal guadalupe",
        999001,
        "Terminal Guadalupe",
        "ENTITY",
        ArchiveReviewStatus.AI_APPROVED,
    )

    # A doubt that went to a human, with both sides still alive.
    live_tag, live_entity = _pair(db_session, tag_name="pesquisa", entity_name="Pesquisa", entity_type="PER")
    _judge_row(
        db_session,
        live_tag.tag_id,
        "pesquisa",
        live_entity.entity_id,
        "Pesquisa",
        "TAG",
        ArchiveReviewStatus.NEEDS_REVIEW,
        confidence=0.55,
    )

    page = repo.list_judged_conflicts()

    assert page.total == 2
    assert page.auto_resolved == 1
    assert page.sent_to_human == 1
    assert page.tag_wins == 1
    assert page.entity_wins == 1
    assert page.still_applicable == 1

    by_name = {item.tag_name: item for item in page.items}
    auto = by_name["terminal guadalupe"]
    assert auto.judge_winner == "ENTITY"
    assert auto.entity_alive is False
    assert auto.applicable is False
    assert auto.judge_reason == "Regra 1 - Bairro é local palpável."

    doubt = by_name["pesquisa"]
    assert doubt.tag_alive and doubt.entity_alive
    assert doubt.applicable is True
    assert doubt.judge_confidence == pytest.approx(0.55)


def test_the_live_page_carries_the_verdict_and_separates_the_two_populations(
    use_test_db, db_session, generate_archive_doc
):
    """
    ``pair_kind`` is what makes the queue usable: the same spelling on both axes is a structural
    question, a different spelling is a spelling question. On the real collection that is 5 050
    against 122, and mixed together the archivist cannot see the real work.
    """
    repo = EntityRepository(db_session)

    # Exact name: same spelling on both axes.
    exact_tag, exact_entity = _pair(db_session, tag_name="batel", entity_name="batel")
    # Near duplicate: the same word written differently (a street abbreviation, the real pattern).
    near_tag = ArchiveTag(name="rua visc. visconde de guarapuava")
    near_entity = ArchiveEntity(name="Rua Visconde De Guarapuava", entity_type="LOC")
    db_session.add_all([near_tag, near_entity])
    db_session.flush()

    _judge_row(
        db_session,
        exact_tag.tag_id,
        "batel",
        exact_entity.entity_id,
        "batel",
        "ENTITY",
        ArchiveReviewStatus.AI_APPROVED,
    )

    page = repo.page_cross_domain_conflicts(threshold=0.6)

    assert page.total == 2
    assert page.exact_name_count == 1
    assert page.near_duplicate_count == 1
    assert page.judged_count == 1

    exact = next(row for row in page.items if row.pair_kind == "EXACT_NAME")
    assert exact.judge_winner == "ENTITY"
    assert exact.judge_status == str(ArchiveReviewStatus.AI_APPROVED)

    near = next(row for row in page.items if row.pair_kind == "NEAR_DUPLICATE")
    assert near.judge_winner is None

    # The scope filter is the lever the screen uses, and the counts follow it.
    only_near = repo.page_cross_domain_conflicts(threshold=0.6, pair_kind="near_duplicate")
    assert only_near.total == 1
    assert only_near.items[0].pair_kind == "NEAR_DUPLICATE"
    assert only_near.exact_name_count == 0

    # Pagination slices the page without changing the totals.
    first = repo.page_cross_domain_conflicts(threshold=0.6, limit=1, offset=0)
    assert len(first.items) == 1
    assert first.total == 2


def test_an_active_resolution_leaves_the_live_scan_and_an_undone_one_comes_back(
    use_test_db, db_session, generate_archive_doc
):
    """
    A resolved pair is *gone* from the live scan, and that is the whole reason the ledger exists.

    The resolution deletes the loser, so the trigram join can no longer produce the pair — there is
    nothing to annotate. Undoing it restores the row and the pair reappears, which is exactly what
    must happen: an undone resolution is history, not a settled pair.
    """
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    doc = generate_archive_doc(original_title="Doc")
    _link_entity(db_session, entity, doc.description_id)
    db_session.flush()

    data = repo.apply_conflict_resolution(repo.plan_conflict_resolution(tag.tag_id, entity.entity_id), "TAG")
    db_session.flush()

    # The entity is gone, so the live scan has nothing to return for this pair.
    assert repo.page_cross_domain_conflicts(threshold=0.6).total == 0

    assert data.resolution_id is not None
    repo.undo_conflict_resolution(data.resolution_id)
    db_session.flush()

    page = repo.page_cross_domain_conflicts(threshold=0.6)
    row = next(item for item in page.items if item.tag_id == tag.tag_id)
    # Back in the scan, and *not* marked as settled: the verdict is the archivist's again.
    assert row.resolution_id is None
    assert row.resolution_winner is None


def test_the_ledger_lists_what_was_written_and_can_filter_the_undone(use_test_db, db_session, generate_archive_doc):
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    doc = generate_archive_doc(original_title="Doc")
    _link_entity(db_session, entity, doc.description_id)
    db_session.flush()

    data = repo.apply_conflict_resolution(
        repo.plan_conflict_resolution(tag.tag_id, entity.entity_id),
        "TAG",
        source="JUDGE",
        decided_by=Author(name="juiz"),
    )
    db_session.flush()

    items, total = repo.list_conflict_resolutions()
    assert total == 1
    entry = items[0]
    assert entry.resolution_id == data.resolution_id
    assert entry.winner == "TAG"
    assert entry.source == "JUDGE"
    assert entry.documents_transferred == 1
    assert entry.ban_kind == "NER_EXCLUSION"
    assert entry.ban_created is True
    assert entry.decided_by == "juiz"
    assert entry.is_undone is False

    assert data.resolution_id is not None
    repo.undo_conflict_resolution(data.resolution_id)
    db_session.flush()

    active, active_total = repo.list_conflict_resolutions(include_undone=False)
    assert active_total == 0
    assert active == []

    all_items, all_total = repo.list_conflict_resolutions(include_undone=True)
    assert all_total == 1
    assert all_items[0].is_undone is True
    assert all_items[0].loser_restored is True


def test_resolving_through_the_single_entry_point_always_leaves_a_ledger_row(
    use_test_db, db_session, generate_archive_doc
):
    """
    The judge's auto-resolution goes through the ledger too.

    It used to call the raw transfer, which left no trace — so the 84 auto-resolutions on the real
    collection were irreversible. There is one write path now, and it always records.
    """
    repo = EntityRepository(db_session)
    tag, entity = _pair(db_session)
    doc = generate_archive_doc(original_title="Doc")
    _link_entity(db_session, entity, doc.description_id)
    db_session.flush()

    transferred = repo.resolve_cross_domain_conflict("TAG", tag.tag_id, entity.entity_id, source="JUDGE")
    db_session.flush()

    assert transferred == 1
    items, total = repo.list_conflict_resolutions()
    assert total == 1
    assert items[0].source == "JUDGE"
    assert items[0].winner == "TAG"
