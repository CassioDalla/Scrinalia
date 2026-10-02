from sqlalchemy import select

from domains.archive.models import (
    ArchiveDocument,
    ArchiveReviewStatus,
)
from domains.archive.repository.document_repo import DocumentRepository
from domains.archive.schemas.command_schema import DocumentReviewCommand

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
# AI TESTS
# ==========================================


def test_stamp_ai_execution(use_test_db, db_session, generate_archive_dto):
    """Tests whether the mutable JSONB column saves the new log, preserving the ORM state."""
    repo = DocumentRepository(db_session)
    dto = generate_archive_dto(description_id="27", execution_log={"migracao_base": "DONE"})
    repo.upsert_archive_document(dto)
    db_session.commit()

    repo.stamp_ai_execution("27", "ner_spacy_v1")
    db_session.commit()

    doc_db = db_session.execute(select(ArchiveDocument).filter_by(description_id="27")).scalar_one()

    assert "migracao_base" in doc_db.execution_log
    assert doc_db.execution_log["ner_spacy_v1"] == "DONE"


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
