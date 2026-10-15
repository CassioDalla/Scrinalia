from unittest.mock import patch

from scrinalia.domains.archive.engines.classification import registry as typology_registry
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.archive.worker_stamp import TYPOLOGY
from scrinalia.domains.archive.workers.worker_typology import execute, producer_identity


def _identity(columns: tuple[str, ...] = ("original_title",)) -> str:
    """The stamp the run under test writes: the fake engine, the fake preset and the default floor."""
    return producer_identity(
        engine_name="motor_fake",  # type: ignore[arg-type]
        preset="preset_teste",  # type: ignore[arg-type]
        columns_to_classify=list(columns),
        confidence_threshold=0.40,
        engine_kwargs={},
    )


def test_worker_typology_integration_skips_human_approved(
    use_test_db,
    db_session,
    generate_archive_doc,
    generate_typology,
    mock_registry,
):
    """Governance: human curation blocks AI reclassification."""
    real_typology = generate_typology(id=99, name="dossiê")
    approved = generate_archive_doc(
        original_title="Documento revisado",
        scope_content="Conteúdo já validado.",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.return_value = [{"labels": [real_typology.name], "scores": [0.99]}]

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )

    ai_instance.classify.assert_not_called()
    db_session.expire_all()
    assert db_session.get(ArchiveDocument, approved.description_id).typology_id is None


def test_worker_integration_updates_database_correctly(
    use_test_db,
    db_session,
    generate_archive_doc,
    generate_typology,
    mock_registry,
):
    # 1. Real preparation in the database
    real_typology = generate_typology(id=99, name="dossiê")
    real_doc = generate_archive_doc(original_title="Dossiê do Servidor João", scope_content="Documentos admissionais.")

    doc_id = real_doc.description_id
    expected_typology_id = real_typology.typology_id

    # 2. Prepare the Fake AI
    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.return_value = [{"labels": [real_typology.name], "scores": [0.85]}]

    # 3. Action: We pass the isolated Pytest db_session straight to the worker!
    execute(
        db=db_session,  # <--- Clean injection in the test
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )

    # 4. Checks (Asserts)

    updated_doc = db_session.get(ArchiveDocument, doc_id)

    assert updated_doc.typology_id == expected_typology_id
    # The stamp names the producer, not the fact that it ran: a second run with the same
    # engine is free, and the queue is empty afterwards.
    assert updated_doc.execution_log[TYPOLOGY.key] == _identity(("original_title", "scope_content"))


def test_worker_exits_gracefully_without_typologies(db_session, mock_registry):
    # The database is empty (no typology created)
    MockClass = mock_registry(typology_registry)
    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    # The test passes simply if the function runs to the end without raising exceptions.
    # The log "Nenhuma tipologia cadastrada" will be emitted internally.
    ai_instance = MockClass.return_value
    ai_instance.classify.assert_not_called()


def test_worker_exits_gracefully_without_pending_documents(
    db_session, generate_typology, generate_archive_doc, mock_registry
):
    generate_typology(id=1, name="Dossiê")

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value

    # A document already stamped **by this producer** is out of the queue. A stamp from another
    # producer — including the legacy ``DONE`` — is pending again, which is what makes a
    # classification revisable.
    generate_archive_doc(execution_log={TYPOLOGY.key: _identity()})

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    # The AI must not be triggered, since the database Where filtered the document
    ai_instance.classify.assert_not_called()


def test_worker_ignores_empty_documents_and_stamps_the_identity(
    db_session, generate_typology, generate_archive_doc, mock_registry
):
    generate_typology(id=1, name="Dossiê")

    # Document without useful text (Null in one column and empty in the other)
    doc = generate_archive_doc(original_title="", scope_content="   ")
    doc_id = doc.description_id

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )

    # The AI cannot receive empty strings
    ai_instance.classify.assert_not_called()

    # But the document MUST be stamped so it does not loop on the next round
    updated_doc = db_session.get(ArchiveDocument, doc_id)
    assert updated_doc.typology_id is None
    assert updated_doc.execution_log[TYPOLOGY.key] == _identity(("original_title", "scope_content"))


def test_worker_ignores_low_ai_confidence(db_session, generate_typology, generate_archive_doc, mock_registry):
    typology = generate_typology(id=1, name="Dossiê")
    doc = generate_archive_doc(original_title="Texto confuso sem contexto")
    doc_id = doc.description_id

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value

    # AI returns only 30% confidence (your threshold is 40%)
    ai_instance.classify.return_value = [{"labels": [typology.name], "scores": [0.30]}]

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    updated_doc = db_session.get(ArchiveDocument, doc_id)

    # It must not file
    assert updated_doc.typology_id is None
    # It must be stamped with the producer identity, so a *different* threshold re-reads it
    assert updated_doc.execution_log[TYPOLOGY.key] == _identity()


def test_worker_handles_ai_hallucination(db_session, generate_typology, generate_archive_doc, mock_registry):
    generate_typology(id=1, name="Dossiê")
    doc = generate_archive_doc(original_title="Documento normal")
    doc_id = doc.description_id

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value

    # AI returns an invented label that does not exist in the database map
    ai_instance.classify.return_value = [{"labels": ["Tipologia Inexistente"], "scores": [0.99]}]

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    updated_doc = db_session.get(ArchiveDocument, doc_id)

    # It cannot break with KeyError, it must remain null
    assert updated_doc.typology_id is None
    assert updated_doc.execution_log[TYPOLOGY.key] == _identity()


def test_worker_rolls_back_on_ai_failure(db_session, generate_typology, generate_archive_doc, mock_registry):
    generate_typology(id=1, name="Dossiê")
    doc = generate_archive_doc(original_title="Texto gigante")
    doc_id = doc.description_id

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value

    # We simulate the HuggingFace model running out of memory (OOM)
    ai_instance.classify.side_effect = Exception("CUDA Out of Memory")

    # The worker must catch the error internally and break the loop safely
    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    updated_doc = db_session.get(ArchiveDocument, doc_id)

    # Since a rollback and break occurred at AI processing time, the document
    # must remain untouched in the database (no stamp) to be retried later.
    assert updated_doc.typology_id is None
    assert updated_doc.execution_log is None or "worker_typology_classifier_v2" not in updated_doc.execution_log


def test_worker_rolls_back_on_commit_failure(db_session, generate_typology, generate_archive_doc, mock_registry):
    typology = generate_typology(id=1, name="Dossiê")
    doc = generate_archive_doc(original_title="Documento perfeito")
    doc_id = doc.description_id

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.return_value = [{"labels": [typology.name], "scores": [0.90]}]

    # We use patch.object to intercept EXACTLY the commit method of our current session
    with patch.object(db_session, "commit", side_effect=Exception("Conexão com PostgreSQL perdida")):
        # The worker will classify, stamp in memory and try to commit, but it will blow up with an error
        execute(
            db=db_session,
            engine_name="motor_fake",  # type: ignore
            preset="preset_teste",  # type: ignore
        )

    # Your worker's rollback kicks in. The document returns to its original state.
    updated_doc = db_session.get(ArchiveDocument, doc_id)

    assert updated_doc.typology_id is None
    assert updated_doc.execution_log is None or "worker_typology_classifier_v2" not in updated_doc.execution_log


BLOCK = "Acervo de 35.327 fotografias que retratam a cidade de Curitiba no âmbito do Planejamento"


def test_worker_typology_classifies_the_text_without_the_approved_excerpt(
    use_test_db,
    db_session,
    generate_archive_doc,
    generate_typology,
    mock_registry,
):
    """Fase 3.5-B: the shared boilerplate is what pulled every document to the same label."""
    from scrinalia.domains.archive.repository.text_quality_repo import TextQualityRepository
    from scrinalia.domains.archive.schemas.text_quality_schema import TemplateCreateCommand

    real_typology = generate_typology(id=97, name="dossiê")
    generate_archive_doc(description_id="typ_cut", original_title="Rua Izaac", scope_content=BLOCK)
    TextQualityRepository(db_session).create_template(TemplateCreateCommand(text=BLOCK))

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.return_value = [{"labels": [real_typology.name], "scores": [0.99]}]

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )

    assert ai_instance.classify.call_args.args[0] == ["Rua Izaac"]


# ==========================================
# THE STAMP NAMES THE PRODUCER (issue 70)
# ==========================================


def test_a_different_threshold_requeues_the_refused_documents(
    use_test_db, db_session, generate_archive_doc, generate_typology, mock_registry
):
    """
    A value measured by the bench has to reach the collection without editing code.

    The document scores 0.50: the 0.60 floor refuses it and stamps that producer, so lowering the
    floor to 0.40 changes the identity and the document is pending again — which a status stamp
    could never do, and the reason the threshold used to be unreachable.
    """
    typology = generate_typology(id=98, name="dossiê")
    # Read eagerly: the worker calls ``expunge_all()`` and detaches the instances.
    typology_name, typology_id = typology.name, typology.typology_id
    doc = generate_archive_doc(description_id="typ_thr", original_title="Documento mediano")
    doc_id = doc.description_id

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.return_value = [{"labels": [typology_name], "scores": [0.50]}]

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", confidence_threshold=0.60)  # type: ignore

    db_session.expire_all()
    assert db_session.get(ArchiveDocument, doc_id).typology_id is None

    ai_instance.classify.reset_mock()
    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", confidence_threshold=0.40)  # type: ignore

    # The document came back by itself, and the lower floor links it now.
    ai_instance.classify.assert_called_once()
    db_session.expire_all()
    assert db_session.get(ArchiveDocument, doc_id).typology_id == typology_id

    # And it is settled under the producer that linked it: a third run is free.
    ai_instance.classify.reset_mock()
    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", confidence_threshold=0.40)  # type: ignore
    ai_instance.classify.assert_not_called()


def test_a_forced_run_advances_by_cursor_and_honours_the_limit(
    use_test_db, db_session, generate_archive_doc, generate_typology, mock_registry
):
    """
    ``force`` drops the stamp clause, so the loop needs the cursor to end — and the cap to be cheap.

    With two documents, a batch of one and a cap of two, a run without the cursor would re-read the
    first document forever and never reach the second.
    """
    typology = generate_typology(id=96, name="dossiê")
    # Read eagerly: the worker calls ``expunge_all()`` and detaches the instances.
    typology_name, typology_id = typology.name, typology.typology_id
    first = generate_archive_doc(description_id="typ_a", original_title="Primeiro")
    second = generate_archive_doc(description_id="typ_b", original_title="Segundo")
    first_id, second_id = first.description_id, second.description_id

    MockClass = mock_registry(typology_registry)
    ai_instance = MockClass.return_value
    ai_instance.classify.side_effect = lambda texts, candidate_labels, **kwargs: [
        {"labels": [typology_name], "scores": [0.99]} for _ in texts
    ]

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", force=True, limit=2, db_batch_size=1)  # type: ignore

    assert ai_instance.classify.call_count == 2
    db_session.expire_all()
    assert db_session.get(ArchiveDocument, first_id).typology_id == typology_id
    assert db_session.get(ArchiveDocument, second_id).typology_id == typology_id
