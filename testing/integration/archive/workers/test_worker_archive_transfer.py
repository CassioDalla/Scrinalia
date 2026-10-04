from sqlalchemy import select

from memoria_curitibana.domains.archive.models import ArchiveDocument, ArchiveDocumentTag, ArchiveTag
from memoria_curitibana.domains.archive.ports.staging_source import StagingRecord
from memoria_curitibana.domains.archive.workers import worker_archive_transfer
from memoria_curitibana.domains.staging.models import StagingDocument


def test_integration_worker_etl_end_to_end(use_test_db, db_session):
    """
    Tests the complete Ingestion pipeline (End-to-End).
    Guarantees that the data leaves Staging, goes through the validations,
    tag extraction and arrives intact in the Fact tables (Archive).
    """
    # 1. SETUP: We create dirty data in Staging (simulating reality)
    doc1 = StagingDocument(
        description_id="br_pr_123",
        title="  Ata da Reunião  ",  # Title with extra spaces
        raw_content_hash="hash_novo_1",
        scope_content="Conteúdo válido",
        indexing_points="Urbanismo, Obras, Lixo, ",  # Has useful tags and junk
    )
    doc2 = StagingDocument(
        description_id="br_pr_456",
        title="Decreto Municipal",
        raw_content_hash="hash_novo_2",
        scope_content="Outro conteúdo",
        indexing_points="Obras, Prefeito",  # "Obras" repeated in the batch to test the deduplicated Bulk Insert
    )

    db_session.add_all([doc1, doc2])

    # Let's take the opportunity to register 'Lixo' as a stopword to see the magic happen
    from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository

    TagRepository(db_session).save_stopwords(["lixo"])
    db_session.commit()

    # 2. ACTION: We run the orchestrator against the real database
    worker_archive_transfer.execute(db_session)

    # 3. DOCUMENT VALIDATION
    migrated_docs = db_session.scalars(select(ArchiveDocument).order_by(ArchiveDocument.description_id)).all()
    assert len(migrated_docs) == 2

    # Validating whether the title ended up in the right place (even with the dirty spaces, the DTO must have passed)
    doc_1_db = next(d for d in migrated_docs if d.description_id == "br_pr_123")
    assert doc_1_db.original_title == "  Ata da Reunião  "
    # The archive CDC key is the hash of what staging *parsed*, not of the raw payload:
    # otherwise a parser fix could never reach this layer.
    assert doc_1_db.staging_content_hash == StagingRecord.model_validate(doc1).parsed_content_hash()
    assert doc_1_db.staging_content_hash != "hash_novo_1"

    # 4. TAG VALIDATION (Creation and Cleaning)
    generated_tags = db_session.scalars(select(ArchiveTag.name)).all()

    # "Lixo" must have disappeared. "Obras" must have been deduplicated. Remaining: urbanismo, obras, prefeito
    assert len(generated_tags) == 3
    assert "urbanismo" in generated_tags
    assert "obras" in generated_tags
    assert "prefeito" in generated_tags
    assert "lixo" not in generated_tags

    # 5. N:N LINK VALIDATION (Did the Bulk Insert optimization work?)
    links = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert len(links) == 4  # 2 from the first doc + 2 from the second doc


def test_integration_worker_etl_ignores_repeated_documents(use_test_db, db_session):
    """
    Tests Idempotency against the real database.
    Guarantees that if the Worker runs twice, it does not duplicate data or blow up with errors.
    """
    # 1. SETUP: Document in Staging
    doc = StagingDocument(
        description_id="doc_idempotente", title="Fixo", raw_content_hash="hash_imutavel", indexing_points="Tag_A"
    )
    db_session.add(doc)
    db_session.commit()

    # 2. ACTION 1: Run the first time (Initial Load)
    worker_archive_transfer.execute(db_session)

    doc_count_1 = db_session.query(ArchiveDocument).count()
    tag_count_1 = db_session.query(ArchiveTag).count()
    link_count_1 = db_session.query(ArchiveDocumentTag).count()

    # 3. ACTION 2: Run the second time (Reprocessing)
    worker_archive_transfer.execute(db_session)

    doc_count_2 = db_session.query(ArchiveDocument).count()
    tag_count_2 = db_session.query(ArchiveTag).count()
    link_count_2 = db_session.query(ArchiveDocumentTag).count()

    # 4. VALIDATION: The database must be exactly the same, nothing may have been created on the second pass
    assert doc_count_1 == 1 and doc_count_2 == 1
    assert tag_count_1 == 1 and tag_count_2 == 1
    assert link_count_1 == 1 and link_count_2 == 1
