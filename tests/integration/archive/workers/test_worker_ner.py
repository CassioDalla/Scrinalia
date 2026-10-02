from unittest.mock import patch

from sqlalchemy import select

from domains.archive.models import ArchiveDocument, ArchiveDocumentEntity, ArchiveEntity, ArchiveReviewStatus
from domains.archive.schemas.entity_schema import ArchiveEntityDTO
from domains.archive.workers.worker_ner import execute


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_skips_human_approved(
    mock_get_engine,
    db_session,
    generate_archive_doc,
):
    """Governance: a HUMAN_APPROVED document must be shielded from AI re-processing."""
    generate_archive_doc(
        description_id="doc_human",
        original_title="Documento revisado pelo arquivista",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )

    execute(db=db_session)

    # The AI must never even be consulted for a human-approved document.
    mock_get_engine.return_value.extract.assert_not_called()

    db_session.expire_all()
    approved = db_session.get(ArchiveDocument, "doc_human")
    assert approved.execution_log is None or "worker_ner_v1" not in approved.execution_log


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_real_database(
    mock_get_engine,
    db_session,  # Your injected PostgreSQL session!
    generate_archive_doc,  # Your document factory
):
    """Integration: Tests the real SQL for inserting Entities and manipulating the JSONB field."""
    ner_engine_mock = mock_get_engine.return_value

    # 1. AI MOCK: We simulate the AI finding 2 entities in the text
    ner_engine_mock.extract.return_value = [
        [
            ArchiveEntityDTO(name="David Carneiro", entity_type="PER"),
            ArchiveEntityDTO(name="Curitiba", entity_type="LOC"),
        ]
    ]

    # 2. SETUP: We insert a real document into PostgreSQL
    real_doc = generate_archive_doc(
        description_id="doc_ner_1",
        original_title="Relatório Anual",
        scope_content="Documento emitido na cidade de Curitiba por David Carneiro.",
    )
    db_session.add(real_doc)
    db_session.commit()

    # 3. ACTION: The Worker runs using the real session (we do NOT mock the repository!)
    execute(db=db_session)

    # 4. CHECKS: Document updated
    db_session.expire_all()  # Clears the cache to force a fresh read from the database
    updated_doc = db_session.get(ArchiveDocument, "doc_ner_1")

    # Checks whether the JSONB was written perfectly to disk
    assert updated_doc.execution_log is not None
    assert updated_doc.execution_log["worker_ner_v1"] == "DONE"

    # Confirms the correct sending of the concatenated text to the AI
    args, _ = ner_engine_mock.extract.call_args
    assert args[0] == ["Relatório Anual. Documento emitido na cidade de Curitiba por David Carneiro."]

    # 5. CHECKS: Did the database receive the correct inserts?
    db_entities = db_session.scalars(select(ArchiveEntity)).all()
    assert len(db_entities) == 2
    names = {e.name for e in db_entities}

    # Entity names are normalized to lowercase on persistence.
    assert "david carneiro" in names
    assert "curitiba" in names

    # Checks whether the associative table (N:N) was populated
    links = db_session.scalars(select(ArchiveDocumentEntity)).all()
    assert len(links) == 2


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_ignores_already_processed_documents(mock_get_engine, db_session, generate_archive_doc):
    """Integration: Validates whether the SQLAlchemy WHERE query respects the JSONB negation in PostgreSQL."""
    # We insert a document into the real database that ALREADY HAS the stamp
    old_doc = generate_archive_doc(
        original_title="Documento Antigo", execution_log={"worker_ner_v1": "DONE", "algum_outro_worker": "ERROR"}
    )
    db_session.add(old_doc)
    db_session.commit()

    # Run the orchestrator
    execute(db=db_session)

    # Checks whether the AI was completely ignored, since the database query must have returned empty
    mock_get_engine.return_value.extract.assert_not_called()


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_processes_multiple_batches(mock_get_engine, db_session, generate_archive_doc):
    """Integration: Validates whether the 'while True' advances correctly through the limit pages in the DB."""
    ner_engine_mock = mock_get_engine.return_value

    # We create 3 documents in the database
    docs = [
        generate_archive_doc(description_id="doc-1", original_title="Texto 1"),
        generate_archive_doc(description_id="doc-2", original_title="Texto 2"),
        generate_archive_doc(description_id="doc-3", original_title="Texto 3"),
    ]
    db_session.add_all(docs)
    db_session.commit()

    # The AI Mock must return empty entity lists consistent with the batches.
    # Batch 1 has 2 documents (returns [[], []]). Batch 2 has 1 document (returns [[]]).
    ner_engine_mock.extract.side_effect = [[[], []], [[]]]

    # We run forcing a tiny batch_size of 2
    # This will force the worker to take 2 turns around the while loop
    execute(db=db_session, db_batch_size=2)

    db_session.expire_all()

    # All 3 documents must have the DONE stamp saved in the database
    assert db_session.get(ArchiveDocument, "doc-1").execution_log["worker_ner_v1"] == "DONE"
    assert db_session.get(ArchiveDocument, "doc-2").execution_log["worker_ner_v1"] == "DONE"
    assert db_session.get(ArchiveDocument, "doc-3").execution_log["worker_ner_v1"] == "DONE"

    # The AI inference (batch extract) must have been called exactly 2 times
    assert ner_engine_mock.extract.call_count == 2


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_ignores_fully_null_rows(mock_get_engine, db_session, generate_archive_doc):
    """Integration: Validates the assembly of the dynamic or_() in SQLAlchemy. Docs without texts do not enter the queue."""
    # Document where the fields we asked to extract are explicitly None
    ghost_doc = generate_archive_doc(
        description_id="doc_fantasma",
        original_title="Titulo teste doc",
        admin_bio_history=None,
        provenance=None,
        scope_content=None,
    )
    db_session.add(ghost_doc)
    db_session.commit()

    # We run the worker asking it to look ONLY at the fields we know are None
    execute(db=db_session, columns_to_extract=["scope_content", "admin_bio_history"])

    # The database query must summarily ignore this row in or_(*filters)
    mock_get_engine.return_value.extract.assert_not_called()

    # The document in the database must remain untouched (no execution_log created)
    db_session.expire_all()
    verified_doc = db_session.get(ArchiveDocument, "doc_fantasma")
    assert verified_doc.execution_log is None or "worker_ner_v1" not in verified_doc.execution_log
