from sqlalchemy import select

from scrinalia.domains.archive.models import ArchiveDocument, ArchiveDocumentTag, ArchiveTag
from scrinalia.domains.archive.ports.staging_source import StagingRecord
from scrinalia.domains.archive.workers import worker_archive_transfer
from scrinalia.domains.staging.models import StagingDocument


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
    from scrinalia.domains.archive.repository.tag_repo import TagRepository

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


# ==========================================
# H6 — THE PARENT THE ORIGIN DECLARES
# ==========================================
def test_the_declared_parent_is_linked_and_the_path_follows(db_session, use_test_db):
    """
    A child that declares its parent is loaded under it, with the path the arrangement implies.

    This is the whole point of the ingestion contract: the tree stops being derived and starts being
    declared — when the origin declares it.
    """
    from scrinalia.domains.archive.worker_stamp import HIERARCHY_PARENT, HIERARCHY_PARENT_RESOLVED

    db_session.add_all(
        [
            StagingDocument(
                description_id="pai",
                title="Fundo SMU",
                raw_content_hash="h1",
                reference_code="BR PRADAP SMU",
            ),
            StagingDocument(
                description_id="filho",
                title="Série Alvenaria",
                raw_content_hash="h2",
                reference_code="BR PRADAP SMU AL",
                parent_reference_code="BR PRADAP SMU",
            ),
        ]
    )
    db_session.commit()

    worker_archive_transfer.execute(db_session)

    child = db_session.get(ArchiveDocument, "filho")
    assert child is not None
    assert child.parent_id == "pai"
    assert child.path == "pai.filho"
    assert child.execution_log[HIERARCHY_PARENT.key] == f"{HIERARCHY_PARENT_RESOLVED}pai"


def test_a_parent_that_has_not_arrived_does_not_fail_the_load(db_session, use_test_db):
    """
    The origin may deliver the child before the parent, and the batch must survive it.

    The child enters as a root and **marked**, so the retry can find it instead of it silently
    becoming a permanent orphan.
    """
    from scrinalia.domains.archive.worker_stamp import HIERARCHY_PARENT, HIERARCHY_PARENT_PENDING

    db_session.add(
        StagingDocument(
            description_id="orfao",
            title="Série sem pai",
            raw_content_hash="h1",
            reference_code="BR PRADAP SMU AL",
            parent_reference_code="BR PRADAP SMU",
        )
    )
    db_session.commit()

    worker_archive_transfer.execute(db_session)

    orphan = db_session.get(ArchiveDocument, "orfao")
    assert orphan is not None
    assert orphan.parent_id is None
    assert orphan.path == "orfao"
    assert orphan.execution_log[HIERARCHY_PARENT.key] == f"{HIERARCHY_PARENT_PENDING}BR PRADAP SMU"


def test_the_late_parent_links_the_child_that_was_waiting(db_session, use_test_db):
    """
    "Orphan and marked" is only honest if something comes back for it.

    The parent arrives in a **later** run — which the CDC guard would otherwise never re-process —
    and the retry pass at the end of that run links the child that was already waiting.
    """
    from scrinalia.domains.archive.worker_stamp import HIERARCHY_PARENT, HIERARCHY_PARENT_RESOLVED

    db_session.add(
        StagingDocument(
            description_id="filho-tardio",
            title="Série",
            raw_content_hash="h1",
            reference_code="BR PRADAP SMMA AL",
            parent_reference_code="BR PRADAP SMMA",
        )
    )
    db_session.commit()
    worker_archive_transfer.execute(db_session)
    assert db_session.get(ArchiveDocument, "filho-tardio").parent_id is None

    # The parent only now.
    db_session.add(
        StagingDocument(
            description_id="pai-tardio",
            title="Fundo SMMA",
            raw_content_hash="h2",
            reference_code="BR PRADAP SMMA",
        )
    )
    db_session.commit()
    worker_archive_transfer.execute(db_session)

    child = db_session.get(ArchiveDocument, "filho-tardio")
    assert child is not None
    assert child.parent_id == "pai-tardio"
    assert child.path == "pai-tardio.filho-tardio"
    assert child.execution_log[HIERARCHY_PARENT.key] == f"{HIERARCHY_PARENT_RESOLVED}pai-tardio"


def test_the_full_path_is_the_fallback_when_only_the_chain_was_sent(db_session, use_test_db):
    """An origin that knows the whole chain but not the link still says who the parent is."""
    db_session.add_all(
        [
            StagingDocument(description_id="avô", title="Acervo", raw_content_hash="h1", reference_code="BR PRADAP"),
            StagingDocument(
                description_id="neto",
                title="Item",
                raw_content_hash="h2",
                reference_code="BR ITEM 1",
                hierarchy_path="BR PRADAP / BR PRADAP SMMA / BR ITEM 1",
            ),
            StagingDocument(
                description_id="meio", title="Fundo", raw_content_hash="h3", reference_code="BR PRADAP SMMA"
            ),
        ]
    )
    db_session.commit()

    worker_archive_transfer.execute(db_session)

    grandchild = db_session.get(ArchiveDocument, "neto")
    assert grandchild is not None
    assert grandchild.parent_id == "meio"
    assert grandchild.path == "meio.neto"


def test_a_payload_that_says_nothing_leaves_the_curated_arrangement_alone(db_session, use_test_db):
    """
    The governance rule of the transfer, asserted where it can actually break.

    A description the archivist placed must not be detached by the next transfer just because the
    origin stayed silent about the arrangement.
    """
    db_session.add_all(
        [
            StagingDocument(description_id="raiz", title="Acervo", raw_content_hash="h1", reference_code="BR PRADAP"),
            StagingDocument(description_id="colocado", title="Item", raw_content_hash="h2", reference_code="BR ITEM 9"),
        ]
    )
    db_session.commit()
    worker_archive_transfer.execute(db_session)

    placed = db_session.get(ArchiveDocument, "colocado")
    assert placed is not None
    placed.parent_id = "raiz"
    placed.path = "raiz.colocado"
    db_session.commit()

    # A genuine source change: the title is different and the origin declares no parent.
    staging = db_session.get(StagingDocument, "colocado")
    staging.title = "Item corrigido"
    staging.raw_content_hash = "h2-novo"
    db_session.commit()

    worker_archive_transfer.execute(db_session)

    db_session.expire_all()
    again = db_session.get(ArchiveDocument, "colocado")
    assert again is not None
    assert again.original_title == "Item corrigido"  # the source change did arrive
    assert again.parent_id == "raiz"  # the curated placement did not move
    assert again.path == "raiz.colocado"
