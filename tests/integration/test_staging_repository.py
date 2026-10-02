from sqlalchemy import select

from domains.ingestion.models import RawData
from domains.staging.models import StagingDocument
from domains.staging.repository import SqlRawRecordSource, upsert_staging_document
from domains.staging.schemas import StagingDocumentDTO

# ==========================================
# STAGING REPOSITORY TESTS
# ==========================================


def test_get_pending_raw_records_finds_new_document(use_test_db, db_session) -> None:
    """Guarantees that raw data in Ingestion that does not exist in Staging is returned."""

    # 1. Create raw data at the source
    raw_data = RawData(
        description_id="doc-inédito", content_hash="hash-123", raw_title="Título Bruto", payload={"Data": "1990"}
    )
    db_session.add(raw_data)
    db_session.commit()

    # 2. Run the search
    pending = SqlRawRecordSource(db_session).next_batch()

    assert len(pending) == 1
    assert pending[0].description_id == "doc-inédito"
    assert pending[0].content_hash == "hash-123"


def test_get_pending_raw_records_ignores_synced_documents(use_test_db, db_session) -> None:
    """Guarantees that if the hashes match, the document is ignored."""

    raw_data = RawData(description_id="doc-sync", content_hash="hash-igual", payload={})
    # Simulates that Staging already processed this document and stored the same hash
    staging_data = StagingDocument(
        description_id="doc-sync", raw_content_hash="hash-igual", title="Título", raw_metadata={}
    )

    db_session.add_all([raw_data, staging_data])
    db_session.commit()

    pending = SqlRawRecordSource(db_session).next_batch()

    # Should return nothing, since everything is up to date
    assert len(pending) == 0


def test_get_pending_raw_records_detects_hash_change(use_test_db, db_session) -> None:
    """Guarantees that if the content at the city hall changed (different hash), it requests reprocessing."""

    # New hash (just scraped)
    raw_data = RawData(description_id="doc-mudou", content_hash="hash-NOVO", payload={})
    # Old hash (processed last week)
    staging_data = StagingDocument(
        description_id="doc-mudou", raw_content_hash="hash-VELHO", title="Título Antigo", raw_metadata={}
    )

    db_session.add_all([raw_data, staging_data])
    db_session.commit()

    pending = SqlRawRecordSource(db_session).next_batch()

    # It must be picked up, because the hash changed!
    assert len(pending) == 1
    assert pending[0].description_id == "doc-mudou"


def test_upsert_staging_document_updates_existing_record(use_test_db, db_session) -> None:
    """Tests the ON CONFLICT DO UPDATE replacing outdated data."""

    # 1. The database already holds an old version
    old_data = StagingDocument(
        description_id="doc-update", raw_content_hash="hash-VELHO", title="Título Antigo", raw_metadata={}
    )
    db_session.add(old_data)
    db_session.commit()

    # 2. The new Pydantic DTO arrives
    new_dto = StagingDocumentDTO(
        description_id="doc-update", raw_content_hash="hash-NOVO", title="Título Novo Atualizado"
    )

    # 3. Perform the Upsert
    upsert_staging_document(db_session, new_dto)

    # 4. Check whether the database was updated (expire_all is needed to clear the cache)
    db_session.expire_all()
    updated_doc = db_session.execute(select(StagingDocument).filter_by(description_id="doc-update")).scalar_one()

    assert updated_doc.raw_content_hash == "hash-NOVO"
    assert updated_doc.title == "Título Novo Atualizado"


def test_upsert_staging_preserves_created_at_and_absent_fields(use_test_db, db_session) -> None:
    """
    Regression: the ON CONFLICT must not reset ``created_at`` nor null out fields that
    were simply absent from the new payload.
    """

    old_data = StagingDocument(
        description_id="doc-preserve",
        raw_content_hash="hash-VELHO",
        title="Título Antigo",
        reference_code="BR PR CUR",
        producers="Prefeitura de Curitiba",
        raw_metadata={},
    )
    db_session.add(old_data)
    db_session.commit()

    created_at_before = db_session.get(StagingDocument, "doc-preserve").created_at

    # The new payload only brings the title and a new hash.
    new_dto = StagingDocumentDTO(
        description_id="doc-preserve", raw_content_hash="hash-NOVO", title="Título Novo Atualizado"
    )
    upsert_staging_document(db_session, new_dto)

    db_session.expire_all()
    updated_doc = db_session.execute(select(StagingDocument).filter_by(description_id="doc-preserve")).scalar_one()

    assert updated_doc.title == "Título Novo Atualizado"
    assert updated_doc.created_at == created_at_before  # not reset
    assert updated_doc.reference_code == "BR PR CUR"  # absent field preserved
    assert updated_doc.producers == "Prefeitura de Curitiba"
