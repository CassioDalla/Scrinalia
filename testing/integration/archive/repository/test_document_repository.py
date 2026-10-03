from sqlalchemy import select

from memoria_curitibana.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentTag,
    ArchiveMacroCategory,
    ArchiveReviewStatus,
    ArchiveTag,
)
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.schemas.command_schema import DocumentReviewCommand

# ==========================================
# UPSERT AND DATA PIPELINE (ETL) TESTS
# ==========================================


def test_upsert_archive_document_insert_new(use_test_db, db_session, generate_archive_dto):
    """Scenario 1: Insertion of a brand-new document coming from Staging."""
    repo = DocumentRepository(db_session)
    new_dto = generate_archive_dto(description_id="1", original_title="Inédito", staging_content_hash="hash_1")

    inserted = repo.upsert_archive_document(new_dto)
    db_session.commit()

    assert inserted is True
    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="1")).scalar_one()
    assert doc_db.original_title == "Inédito"


def test_upsert_archive_document_ignore_same_hash(use_test_db, db_session, generate_archive_dto):
    """Scenario 2: Incremental Load. A document with the same Hash must be ignored."""
    repo = DocumentRepository(db_session)
    original_dto = generate_archive_dto(description_id="2", original_title="Original", staging_content_hash="hash_2")
    repo.upsert_archive_document(original_dto)
    db_session.commit()

    repeated_dto = generate_archive_dto(description_id="2", original_title="Falso", staging_content_hash="hash_2")
    repeated_inserted = repo.upsert_archive_document(repeated_dto)
    db_session.commit()

    assert repeated_inserted is False
    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="2")).scalar_one()
    assert doc_db.original_title == "Original"


def test_upsert_archive_document_update_resets_ai(use_test_db, db_session, generate_archive_dto):
    """
    Scenario 3: CDC. If the Hash changed in Staging, it updates the data AND erases AI
    traces that ARE present in the new payload (execution_log={} and PENDING_AI here),
    while preserving metadata that this transfer does not carry.
    """
    repo = DocumentRepository(db_session)
    original_dto = generate_archive_dto(
        description_id="3",
        original_title="Antigo",
        staging_content_hash="hash_3",
        execution_log={"ner_spacy_v1": "DONE"},
        review_status=ArchiveReviewStatus.NEEDS_REVIEW,
        reference_code="BR PR CUR 001",
    )
    repo.upsert_archive_document(original_dto)
    db_session.commit()

    new_dto = generate_archive_dto(
        description_id="3",
        original_title="Novo Título",
        staging_content_hash="hash_3_NOVO",
        execution_log={},
        review_status=ArchiveReviewStatus.PENDING_AI,
    )
    new_inserted = repo.upsert_archive_document(new_dto)
    db_session.commit()

    assert new_inserted is True
    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="3")).scalar_one()
    assert doc_db.original_title == "Novo Título"
    assert doc_db.execution_log == {}  # The log present in the payload was reset!
    assert doc_db.review_status == ArchiveReviewStatus.PENDING_AI
    # A field NOT sent by this transfer payload must survive the update.
    assert doc_db.reference_code == "BR PR CUR 001"


def test_upsert_archive_document_preserves_created_at(use_test_db, db_session, generate_archive_dto):
    """Regression: reprocessing a document must not reset its created_at."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="created", original_title="Antigo", staging_content_hash="h1")
    )
    db_session.commit()

    created_at_before = db_session.get(ArchiveDocument, "created").created_at

    repo.upsert_archive_document(
        generate_archive_dto(description_id="created", original_title="Novo", staging_content_hash="h2")
    )
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(ArchiveDocument, "created")
    assert stored.original_title == "Novo"
    assert stored.created_at == created_at_before


def test_upsert_archive_document_blocked_by_human_approved(use_test_db, db_session, generate_archive_dto):
    """Scenario 4: Governance. A document with HUMAN_APPROVED status blocks the ETL overwrite."""
    repo = DocumentRepository(db_session)
    original_dto = generate_archive_dto(
        description_id="4",
        original_title="Revisado Perfeito",
        staging_content_hash="hash_4",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )
    repo.upsert_archive_document(original_dto)
    db_session.commit()

    attack_dto = generate_archive_dto(
        description_id="4", original_title="Lixo da Staging", staging_content_hash="hash_4_NOVO"
    )
    attack_inserted = repo.upsert_archive_document(attack_dto)
    db_session.commit()

    assert attack_inserted is False
    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="4")).scalar_one()
    assert doc_db.original_title == "Revisado Perfeito"


# ==========================================
# READING AND CURATION TESTS
# ==========================================


def test_search_filters_by_term_and_paginates(use_test_db, db_session, generate_archive_dto):
    """Text search returns only the matches and the correct total, respecting the page."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="s1", original_title="Matadouro Municipal", staging_content_hash="h1")
    )
    repo.upsert_archive_document(
        generate_archive_dto(description_id="s2", original_title="Praça do Gaúcho", staging_content_hash="h2")
    )
    db_session.commit()

    docs, total = repo.search(term="Matadouro")
    assert total == 1
    assert docs[0].description_id == "s1"

    page, total_overall = repo.search(limit=1, offset=0)
    assert total_overall == 2
    assert len(page) == 1


def test_update_review_blinds_document_as_human_approved(use_test_db, db_session, generate_archive_dto):
    """Human editing applies the fields and marks the document as HUMAN_APPROVED."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="r1", original_title="Original", staging_content_hash="hr1")
    )
    db_session.commit()

    updated = repo.update_review(
        DocumentReviewCommand(description_id="r1", final_title="Título Revisado", archivist_notes="ok")
    )
    db_session.commit()

    assert updated is not None
    assert updated.review_status == ArchiveReviewStatus.HUMAN_APPROVED
    assert updated.final_title == "Título Revisado"


def test_update_review_returns_none_for_missing_document(use_test_db, db_session):
    repo = DocumentRepository(db_session)
    assert repo.update_review(DocumentReviewCommand(description_id="nao-existe", final_title="x")) is None


# ==========================================
# MACRO CATEGORY VOTE (SUBJECT AXIS)
# ==========================================


def _link_tag(db_session, description_id: str, tag_id: int) -> None:
    db_session.add(ArchiveDocumentTag(description_id=description_id, tag_id=tag_id))


def test_search_votes_macro_categories_by_tag_count(use_test_db, db_session, generate_archive_doc):
    """The read view exposes the winning category first, counting only categorized tags."""
    repo = DocumentRepository(db_session)
    urban = ArchiveMacroCategory(name="Urbanismo")
    health = ArchiveMacroCategory(name="Saúde")
    db_session.add_all([urban, health])
    db_session.flush()

    doc = generate_archive_doc(description_id="vote_1", original_title="Plano Urbano de Curitiba")

    tags = [
        ArchiveTag(name="pavimentação", macro_category_id=urban.category_id),
        ArchiveTag(name="calçamento", macro_category_id=urban.category_id),
        ArchiveTag(name="dengue", macro_category_id=health.category_id),
        ArchiveTag(name="sem categoria", macro_category_id=None),
    ]
    db_session.add_all(tags)
    db_session.commit()

    for tag in tags:
        _link_tag(db_session, doc.description_id, tag.tag_id)
    db_session.commit()

    docs, total = repo.search(term="Plano Urbano")

    assert total == 1
    assert [(vote.name, vote.tag_count) for vote in docs[0].macro_categories] == [("Urbanismo", 2), ("Saúde", 1)]

    detail = repo.get_by_id(doc.description_id)
    assert detail is not None
    assert [(vote.category_id, vote.tag_count) for vote in detail.macro_categories] == [
        (urban.category_id, 2),
        (health.category_id, 1),
    ]


def test_tag_edit_reflects_on_documents_without_touching_the_documents_table(
    use_test_db, db_session, generate_archive_doc
):
    """
    Editing a tag's macro category must be visible on every linked document immediately,
    and must not write to ``archive_documents`` (the vote is derived on read).
    """
    repo = DocumentRepository(db_session)
    urban = ArchiveMacroCategory(name="Urbanismo")
    health = ArchiveMacroCategory(name="Saúde")
    db_session.add_all([urban, health])
    db_session.flush()

    doc = generate_archive_doc(description_id="reflect_1", original_title="Documento Refletido")
    tag = ArchiveTag(name="habitação", macro_category_id=urban.category_id)
    db_session.add(tag)
    db_session.commit()

    _link_tag(db_session, doc.description_id, tag.tag_id)
    db_session.commit()

    before = db_session.get(ArchiveDocument, doc.description_id)
    assert before is not None
    updated_at_before = before.updated_at

    tag.macro_category_id = health.category_id
    db_session.commit()
    db_session.expire_all()

    after = db_session.get(ArchiveDocument, doc.description_id)
    assert after is not None
    assert after.updated_at == updated_at_before

    docs, _ = repo.search(term="Documento Refletido")
    assert [vote.name for vote in docs[0].macro_categories] == ["Saúde"]
