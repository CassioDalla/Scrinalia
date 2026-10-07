import pytest
from sqlalchemy import select, text

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import TagMergeProposalNotFoundError
from scrinalia.domains.archive.models import (
    ArchiveDocumentTag,
    ArchiveMacroCategory,
    ArchiveTag,
    DomainSynonyms,
)
from scrinalia.domains.archive.repository.document_repo import DocumentRepository
from scrinalia.domains.archive.repository.tag_repo import TagRepository
from scrinalia.domains.archive.schemas import (
    ArchiveTagDTO,
    MergeBatchCommand,
    MergePreviewCommand,
    MergeTagsCommand,
    TagMergeDecisionCommand,
)
from scrinalia.domains.archive.schemas.tag_schema import TagRelevanceCount
from scrinalia.domains.archive.services.tag_service import TagService

# ==========================================
# 1. PURGE TESTS (STOPWORDS)
# ==========================================


def test_purge_stopwords_success(use_test_db, db_session):
    """Guarantees that the stopwords are read from the database and deleted."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    # 1. Prepare the database with tags
    db_session.add_all([ArchiveTag(name="ofício"), ArchiveTag(name="valiosa"), ArchiveTag(name="curitiba")])

    # 2. Insert the stopwords into the dictionary (simulating the frontend)
    tag_repo.save_stopwords([" OFÍCIO ", "Curitiba"])
    db_session.commit()

    # 3. The method must read from the database and delete
    deleted = service.purge_stopwords()

    # 4. Since the Service no longer commits, we need to commit the test transaction
    db_session.commit()

    assert deleted == 2
    remaining = db_session.scalars(select(ArchiveTag.name)).all()
    assert remaining == ["valiosa"]


def test_purge_stopwords_cascade(use_test_db, db_session, generate_archive_doc):
    """Guarantees that deleting a tag also destroys the N:N links (Cascade)."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    junk_tag = ArchiveTag(name="lixo")
    doc = generate_archive_doc(description_id="doc_1", original_title="Título Teste")
    db_session.add(junk_tag)
    db_session.commit()

    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=junk_tag.tag_id))
    tag_repo.save_stopwords(["lixo"])
    db_session.commit()

    service.purge_stopwords()
    db_session.commit()  # Persist the deletion

    # The link table must also be empty now
    links = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert len(links) == 0


def test_purge_stopwords_empty_db(use_test_db, db_session):
    """Guarantees that the function returns 0 if it finds nothing."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    deleted = service.purge_stopwords()

    assert deleted == 0


# ==========================================
# 2. COUNT AND STATISTICS TESTS (RELEVANCE)
# ==========================================


def test_get_tag_relevance_count(use_test_db, db_session, generate_archive_doc):
    """Guarantees that the count groups and orders from the most used to the least used."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    common_tag = ArchiveTag(name="comum")
    rare_tag = ArchiveTag(name="rara")
    doc1 = generate_archive_doc(description_id="doc_1", original_title="Doc 1")
    doc2 = generate_archive_doc(description_id="doc_2", original_title="Doc 2")

    db_session.add_all([common_tag, rare_tag])
    db_session.commit()

    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=doc1.description_id, tag_id=common_tag.tag_id),
            ArchiveDocumentTag(description_id=doc2.description_id, tag_id=common_tag.tag_id),
            ArchiveDocumentTag(description_id=doc1.description_id, tag_id=rare_tag.tag_id),
        ]
    )
    db_session.commit()

    results = service.get_tag_relevance_count(limit=5)

    assert len(results) == 2
    expected = [TagRelevanceCount(name="comum", total_usage=2), TagRelevanceCount(name="rara", total_usage=1)]
    assert list(results) == expected


def test_get_tag_relevance_tfidf(use_test_db, db_session, generate_archive_doc):
    """
    Tests the TF-IDF mathematical engine.
    Tags that appear in ALL documents must have an IDF of zero.
    """
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    omnipresent_tag = ArchiveTag(name="onipresente")
    specific_tag = ArchiveTag(name="especifica")
    docs = [generate_archive_doc(description_id=f"doc_{i}", original_title=f"Doc {i}") for i in range(4)]

    db_session.add_all([omnipresent_tag, specific_tag, *docs])
    db_session.commit()

    links = [ArchiveDocumentTag(description_id=d.description_id, tag_id=omnipresent_tag.tag_id) for d in docs]
    links.append(ArchiveDocumentTag(description_id=docs[0].description_id, tag_id=specific_tag.tag_id))
    db_session.add_all(links)
    db_session.commit()

    results = service.get_tag_relevance_tfidf()

    assert len(results) == 2, "Should have evaluated exactly 2 tags"
    first_place, second_place = results[0], results[1]

    assert first_place.name == "especifica"
    assert first_place.score_tfidf > 0.0

    assert second_place.name == "onipresente"
    assert second_place.score_tfidf == 0.0


def test_get_tag_relevance_tfidf_empty_db(use_test_db, db_session):
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    assert service.get_tag_relevance_tfidf() == []


# ==========================================
# 3. APPROXIMATE ALGORITHM TESTS (PG_TRGM)
# ==========================================


def test_find_similar_tags(use_test_db, db_session):
    """Guarantees that the trigram search finds typos and respects the threshold."""
    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    db_session.add_all([ArchiveTag(name="prefeitura"), ArchiveTag(name="prefeituta"), ArchiveTag(name="abacate")])
    db_session.commit()

    similar = service.find_similar_tags("prefeitura", threshold=0.3)

    assert len(similar) == 1
    tag = similar[0]
    assert tag.name == "prefeituta"
    assert tag.similarity > 0.4


# ==========================================
# 4. MERGE TESTS
# ==========================================


def test_merge_tags_success(use_test_db, db_session, generate_archive_doc):
    """Tests the happy flow: moves docs, creates synonyms and deletes the old tag."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    official_tag = ArchiveTag(name="foto")
    wrong_tag = ArchiveTag(name="fotu")
    doc = generate_archive_doc(description_id="doc_1", original_title="Doc Teste")

    db_session.add_all([official_tag, wrong_tag])
    db_session.commit()

    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=wrong_tag.tag_id))
    db_session.commit()

    res = service.merge(MergeTagsCommand(canonical_id=official_tag.tag_id, ids_to_merge=[wrong_tag.tag_id]))
    db_session.commit()  # Commit in the test

    assert res.documents_updated == 1
    assert res.tags_deleted == 1

    synonym = db_session.scalars(select(DomainSynonyms)).first()
    assert synonym.synonym_name == "fotu"
    assert synonym.canonical_tag_id == official_tag.tag_id
    assert synonym.category == "TAG"


def test_merge_tags_idempotency_conflict(use_test_db, db_session, generate_archive_doc):
    """Tests the UniqueConstraint shielding. If the doc already has both tags, it must not explode."""
    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    official_tag = ArchiveTag(name="foto")
    wrong_tag = ArchiveTag(name="fotu")
    doc = generate_archive_doc(description_id="doc_1", original_title="Doc Teste")

    db_session.add_all([official_tag, wrong_tag])
    db_session.commit()

    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=official_tag.tag_id),
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=wrong_tag.tag_id),
        ]
    )
    db_session.commit()

    res = service.merge(MergeTagsCommand(canonical_id=official_tag.tag_id, ids_to_merge=[wrong_tag.tag_id]))
    db_session.commit()  # Commit in the test

    assert res.tags_deleted == 1
    link_count = db_session.query(ArchiveDocumentTag).count()
    assert link_count == 1  # Only the official one remained


def test_chained_merge_keeps_the_mapping_of_the_surviving_canonical(use_test_db, db_session):
    """
    ``a -> b`` followed by ``b -> c`` must not forget that ``a`` was absorbed.

    ``domain_synonyms.canonical_tag_id`` is ``ON DELETE CASCADE``, so deleting ``b`` in the
    second merge used to take the synonym created by the first merge with it. The spelling
    then came back as a brand-new tag at the next ingestion, silently undoing the curation
    the archivist had approved.
    """
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))

    plural = ArchiveTag(name="parques")
    singular = ArchiveTag(name="parque")
    final = ArchiveTag(name="área verde")
    db_session.add_all([plural, singular, final])
    db_session.commit()

    service.merge(MergeTagsCommand(canonical_id=singular.tag_id, ids_to_merge=[plural.tag_id]))
    db_session.commit()
    service.merge(MergeTagsCommand(canonical_id=final.tag_id, ids_to_merge=[singular.tag_id]))
    db_session.commit()

    assert tag_repo.get_synonyms_mapping(["parques", "parque"]) == {
        "parques": final.tag_id,
        "parque": final.tag_id,
    }


def test_no_synonym_points_to_a_deleted_tag_after_a_merge_chain(use_test_db, db_session):
    """The cascade must never leave a synonym whose canonical tag no longer exists."""
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))

    first = ArchiveTag(name="prefeiruta")
    second = ArchiveTag(name="prefeitura")
    third = ArchiveTag(name="prefeitura de curitiba")
    db_session.add_all([first, second, third])
    db_session.commit()

    service.merge(MergeTagsCommand(canonical_id=second.tag_id, ids_to_merge=[first.tag_id]))
    db_session.commit()
    service.merge(MergeTagsCommand(canonical_id=third.tag_id, ids_to_merge=[second.tag_id]))
    db_session.commit()

    dangling = db_session.execute(
        text(
            """
            SELECT count(*) FROM domain_synonyms ds
            WHERE ds.category = 'TAG'
              AND NOT EXISTS (SELECT 1 FROM archive_tags t WHERE t.tag_id = ds.canonical_tag_id)
            """
        )
    ).scalar_one()

    assert dangling == 0


def test_ingestion_after_a_merge_chain_links_the_surviving_canonical(use_test_db, db_session):
    """
    A document arriving with an absorbed spelling must land on the canonical tag.

    This is the prevention half of the dedup: the synonyms written by the merges are what
    stop the ingestion from recreating the duplicate forever.
    """
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))

    plural = ArchiveTag(name="licenças")
    singular = ArchiveTag(name="licença")
    final = ArchiveTag(name="licenciamento")
    db_session.add_all([plural, singular, final])
    db_session.commit()

    service.merge(MergeTagsCommand(canonical_id=singular.tag_id, ids_to_merge=[plural.tag_id]))
    db_session.commit()
    service.merge(MergeTagsCommand(canonical_id=final.tag_id, ids_to_merge=[singular.tag_id]))
    db_session.commit()

    assert service.process_worker_tags([ArchiveTagDTO(name="licenças")]) == [final.tag_id]
    assert "licenças" not in db_session.scalars(select(ArchiveTag.name)).all()


# ==========================================
# MERGE PROPOSALS AND DRY-RUN (Fase 3.5 / Buraco 4)
# ==========================================


def test_preview_merge_is_read_only_and_matches_the_applied_merge(use_test_db, db_session, generate_archive_doc):
    """
    The dry-run never writes, and its numbers are the ones the merge really produces.

    Pinning the two together is the point: a preview that promises something else is worse
    than no preview, because the whole decision rests on it.
    """
    from sqlalchemy import func

    from scrinalia.domains.archive.models import ArchiveTag

    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))

    canonical = ArchiveTag(name="rua")
    variant = ArchiveTag(name="ruas")
    db_session.add_all([canonical, variant])
    db_session.flush()
    for index in range(3):
        doc = generate_archive_doc(original_title=f"Doc {index}")
        db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=variant.tag_id))
    db_session.flush()

    preview = service.preview_merge(MergePreviewCommand(canonical_id=canonical.tag_id, ids_to_merge=[variant.tag_id]))

    assert db_session.scalar(select(func.count()).select_from(ArchiveTag)) == 2  # nothing was deleted

    result = service.merge(MergeTagsCommand(canonical_id=canonical.tag_id, ids_to_merge=[variant.tag_id]))
    db_session.commit()

    assert preview.documents_updated == result.documents_updated == 3
    assert preview.links_rewritten == 3
    assert len(preview.tags_deleted) == result.tags_deleted == 1
    assert preview.synonyms_created == ["ruas"]


def test_suggest_merges_registers_proposals_and_records_the_decision(use_test_db, db_session):
    """The run persists the clusters and the verdict keeps author, time and note."""
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))

    db_session.add_all([ArchiveTag(name="casa"), ArchiveTag(name="casas")])
    db_session.commit()

    run = service.suggest_merges(threshold=0.99)

    assert run.clusters_found == 1
    assert run.persisted == 1
    assert run.pending == 1

    page = service.list_merge_proposals(status="SUGGESTED")
    assert page.total == 1
    proposal = page.items[0]
    assert proposal.canonical_name in {"casa", "casas"}

    decided = service.decide_merge_proposal(
        proposal.proposal_id,
        TagMergeDecisionCommand(status="APPROVED", decided_by=Author(name="arquivista"), note="mesmo conceito"),
    )

    assert decided.status == "APPROVED"
    assert decided.decided_by == "arquivista"
    assert decided.decided_at is not None
    assert decided.decision_note == "mesmo conceito"
    # Recording the verdict does not merge anything: both tags are still there.
    assert set(db_session.scalars(select(ArchiveTag.name)).all()) == {"casa", "casas"}


def test_decide_an_unknown_proposal_raises_a_domain_404(use_test_db, db_session):
    """A PATCH on a proposal that does not exist is a 404, never a silent success."""
    service = TagService(TagRepository(db_session), DocumentRepository(db_session))

    with pytest.raises(TagMergeProposalNotFoundError):
        service.decide_merge_proposal(999_999, TagMergeDecisionCommand(status="REJECTED"))


# ==========================================
# BATCH APPLICATION AND UNDO (the ledger)
# ==========================================


def _clustered_proposals(service: TagService, db_session, pairs: list[tuple[str, str]]) -> list[int]:
    """Creates one tag pair per entry, links a document to the variant and suggests the merges."""
    for canonical_name, variant_name in pairs:
        db_session.add_all([ArchiveTag(name=canonical_name), ArchiveTag(name=variant_name)])
    db_session.commit()

    service.suggest_merges(threshold=0.99)
    return [proposal.proposal_id for proposal in service.list_merge_proposals(status="SUGGESTED").items]


def test_merge_batch_applies_the_clusters_and_records_the_decision(use_test_db, db_session):
    """A pending cluster included in the batch is approved, applied and logged — one savepoint each."""
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))
    proposal_ids = _clustered_proposals(service, db_session, [("casa", "casas"), ("rua", "ruas")])

    result = service.merge_batch(
        MergeBatchCommand(proposal_ids=proposal_ids, changed_by=Author(name="arquivista"), note="mesmo conceito")
    )
    db_session.commit()

    assert [entry.tags_deleted for entry in result.applied] == [1, 1]
    assert result.failed == []
    assert all(entry.merge_ids for entry in result.applied)
    assert tag_repo.count_merge_log() == 2

    # The batch call was the decision **and** the write: the clusters are settled, carry the
    # author, and left the pending queue for good.
    decided = service.list_merge_proposals().items
    assert {proposal.status for proposal in decided} == {"APPLIED"}
    assert {proposal.decided_by for proposal in decided} == {"arquivista"}

    # The merged-away spellings now redirect instead of existing as tags.
    assert set(db_session.scalars(select(ArchiveTag.name)).all()) == {"casa", "rua"}


def test_merge_batch_never_applies_a_rejected_proposal(use_test_db, db_session):
    """Rejecting is a decision too; the batch reports it and leaves the taxonomy alone."""
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))
    proposal_ids = _clustered_proposals(service, db_session, [("lote", "lotes")])

    service.decide_merge_proposal(
        proposal_ids[0], TagMergeDecisionCommand(status="REJECTED", decided_by=Author(name="arquivista"))
    )
    result = service.merge_batch(MergeBatchCommand(proposal_ids=proposal_ids, changed_by=Author(name="arquivista")))
    db_session.commit()

    assert result.applied == []
    assert len(result.failed) == 1
    assert "rejeitada" in result.failed[0].error
    assert set(db_session.scalars(select(ArchiveTag.name)).all()) == {"lote", "lotes"}
    assert tag_repo.count_merge_log() == 0


def test_merge_batch_reports_an_unknown_proposal_and_skips_an_already_applied_one(use_test_db, db_session):
    """
    The batch is per-cluster, and "nothing left to do" is not the same as "it went wrong".

    Applying a cluster a second time used to answer with the same red line as a real error, which is
    how a finished batch of twenty clusters looked like twenty failures. It is now reported apart.
    """
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))
    proposal_ids = _clustered_proposals(service, db_session, [("obra", "obras")])

    first = service.merge_batch(
        MergeBatchCommand(proposal_ids=[*proposal_ids, 999_999], changed_by=Author(name="arquivista"))
    )
    db_session.commit()
    assert len(first.applied) == 1
    assert [failure.proposal_id for failure in first.failed] == [999_999]
    assert first.skipped == []

    # Applying the same cluster again must not silently write a second time — and must not accuse
    # the archivist of a mistake either.
    second = service.merge_batch(MergeBatchCommand(proposal_ids=proposal_ids, changed_by=Author(name="arquivista")))
    db_session.commit()
    assert second.applied == []
    assert second.failed == []
    assert [entry.proposal_id for entry in second.skipped] == proposal_ids
    assert "absorvidos" in second.skipped[0].error
    assert tag_repo.count_merge_log() == 1


def test_an_applied_cluster_leaves_the_approved_queue(use_test_db, db_session):
    """The complaint this fixes: an applied proposal stayed ``APPROVED`` and could never be applied."""
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))
    proposal_ids = _clustered_proposals(service, db_session, [("ponte", "pontes")])

    service.merge_batch(MergeBatchCommand(proposal_ids=proposal_ids, changed_by=Author(name="arquivista")))
    db_session.commit()

    assert service.list_merge_proposals(status="APPROVED").items == []
    applied = service.list_merge_proposals(status="APPLIED").items
    assert [proposal.proposal_id for proposal in applied] == proposal_ids
    # The verdict survives the write: applying does not erase who approved it.
    assert applied[0].decided_by == "arquivista"
    assert applied[0].decided_at is not None


def test_a_proposal_says_whether_there_is_still_work(use_test_db, db_session):
    """
    The members are a snapshot without a foreign key, so the catalogue has to ask the collection.

    Without this the screen offers an apply whose only possible outcome is the failure list.
    """
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))
    proposal_ids = _clustered_proposals(service, db_session, [("muro", "muros")])

    fresh = service.list_merge_proposals(status="SUGGESTED").items[0]
    assert (fresh.members_alive, fresh.canonical_alive, fresh.applicable) == (2, True, True)

    service.merge_batch(MergeBatchCommand(proposal_ids=proposal_ids, changed_by=Author(name="arquivista")))
    db_session.commit()

    done = service.list_merge_proposals(status="APPLIED").items[0]
    assert (done.members_alive, done.canonical_alive, done.applicable) == (1, True, False)


def test_merge_then_undo_restores_the_tag_through_the_service(use_test_db, db_session, generate_archive_doc):
    """The service exposes the ledger: the merge is reversible and the trail says who undid it."""
    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))

    canonical = ArchiveTag(name="edifício")
    variant = ArchiveTag(name="edifícios")
    db_session.add_all([canonical, variant])
    db_session.flush()
    restored_id = variant.tag_id

    doc = generate_archive_doc(original_title="Doc")
    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=variant.tag_id))
    db_session.flush()

    response = service.merge(
        MergeTagsCommand(
            canonical_id=canonical.tag_id, ids_to_merge=[variant.tag_id], changed_by=Author(name="arquivista")
        )
    )
    db_session.flush()
    assert response.merge_ids

    page = service.list_merge_log(canonical_id=canonical.tag_id)
    assert page.total == 1
    assert page.items[0].absorbed_name == "edifícios"
    assert page.items[0].changed_by == "arquivista"

    entry = service.undo_merge(response.merge_ids[0], undone_by=Author(name="outro arquivista"))
    db_session.commit()

    assert entry.is_undone
    assert entry.undone_by == "outro arquivista"
    restored = db_session.get(ArchiveTag, restored_id)
    assert restored is not None and restored.name == "edifícios"
    links = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert [(link.description_id, link.tag_id) for link in links] == [(doc.description_id, restored_id)]


# ==========================================
# TESTS: get_text_to_suggest_macro_category
# ==========================================


def test_integration_get_texts_happy_path_tags(use_test_db, db_session):
    """
    Tests the real integration via Tags.
    Guarantees that it pulls only orphan tags (without a category) for analysis.
    """
    macro = ArchiveMacroCategory(name="Categoria Ignorada", description="Teste")
    db_session.add(macro)
    db_session.flush()

    orphan_tags = [ArchiveTag(name=f"Tag Real {i}", macro_category_id=None) for i in range(12)]
    db_session.add_all(orphan_tags)

    db_session.add(ArchiveTag(name="Tag Ignorada", macro_category_id=macro.category_id))
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    texts = service.get_text_to_suggest_macro_category(source_type="tags")

    assert len(texts) == 12, "Should have pulled only the 12 orphan tags."
    assert "Tag Real 0" in texts
    assert "Tag Ignorada" not in texts


def test_integration_get_texts_happy_path_docs(use_test_db, db_session, generate_archive_doc):
    """
    Tests the real integration via Documents.
    Checks whether the repository concatenates the columns correctly in the database.
    """
    _ = [
        generate_archive_doc(
            description_id=f"doc_{i}",
            original_title=f"Título {i}",
            scope_content="Descrição válida com texto",
            staging_content_hash=f"hash_{i}",
        )
        for i in range(12)
    ]
    # generate_archive_doc usually already commits or attaches to the session. If needed:
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    texts = service.get_text_to_suggest_macro_category(
        source_type="documents", columns_to_extract=["original_title", "scope_content"]
    )

    assert len(texts) == 12
    assert texts[0] == "Título 0. Descrição válida com texto."


def test_integration_get_texts_sad_path_insufficient_tags(use_test_db, db_session):
    """
    Sad Path: There are tags, but fewer than 10.
    The Service returns the short list (the Controller is the one that must block).
    """
    tags = [ArchiveTag(name=f"Tag {i}", macro_category_id=None) for i in range(5)]
    db_session.add_all(tags)
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    texts = service.get_text_to_suggest_macro_category(source_type="tags")

    assert len(texts) == 5


def test_integration_get_texts_sad_path_already_categorized(use_test_db, db_session):
    """
    Sad Path: There are many tags, but all of them already have a Macro Category.
    The database must not return anything.
    """
    macro = ArchiveMacroCategory(name="Categoria Existente", description="Teste")
    db_session.add(macro)
    db_session.flush()

    tags = [ArchiveTag(name=f"Tag {i}", macro_category_id=macro.category_id) for i in range(20)]
    db_session.add_all(tags)
    db_session.commit()

    tag_repo = TagRepository(db_session)
    doc_repo = DocumentRepository(db_session)
    service = TagService(tag_repo, doc_repo)

    texts = service.get_text_to_suggest_macro_category(source_type="tags")

    assert len(texts) == 0, "No tag should have been returned, since they are all already categorized."
    assert texts == []
