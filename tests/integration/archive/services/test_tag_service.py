from sqlalchemy import select, text

from domains.archive.models import ArchiveDocumentTag, ArchiveMacroCategory, ArchiveTag, DomainSynonyms
from domains.archive.repository.document_repo import DocumentRepository
from domains.archive.repository.tag_repo import TagRepository
from domains.archive.schemas import MergeTagsCommand
from domains.archive.schemas.tag_schema import TagRelevanceCount
from domains.archive.services.tag_service import TagService

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
