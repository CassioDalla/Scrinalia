from memoria_curitibana.domains.archive.engines.embeddings import registry as embeddings_registry
from memoria_curitibana.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from memoria_curitibana.domains.archive.workers.worker_embedding import execute

# The fake engine must answer with the column dimension, or PostgreSQL rejects the insert.
VECTOR = [0.0] * 383 + [1.0]


def _fake_engine(mock_registry):
    """Registers the fake embedding engine and answers with a fixed 384-dim vector."""
    MockClass = mock_registry(embeddings_registry)
    instance = MockClass.return_value
    instance.embed.side_effect = lambda texts: [list(VECTOR) for _ in texts]
    return instance


def test_worker_embeds_pending_documents_and_stamps_the_content_hash(
    use_test_db, db_session, mock_registry, generate_archive_doc
):
    generate_archive_doc(description_id="emb1", original_title="Enchentes no Batel", scope_content="alagamento")
    engine = _fake_engine(mock_registry)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, "emb1")
    assert stored is not None
    assert stored.embedding is not None
    assert len(stored.embedding) == 384
    # The stamp is the MD5 of the embedded text, not a status.
    assert len(stored.execution_log["worker_embedding_v1"]) == 32

    # Nothing changed, so a second run must not call the model again.
    engine.embed.reset_mock()
    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore
    engine.embed.assert_not_called()


def test_worker_reembeds_after_a_human_edit_even_when_approved(
    use_test_db, db_session, mock_registry, generate_archive_doc
):
    """The embedding is a derived index: a human edit refreshes it without an AI rewrite."""
    generate_archive_doc(description_id="emb2", original_title="Original", scope_content="texto antigo")
    engine = _fake_engine(mock_registry)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore
    engine.embed.reset_mock()

    doc = db_session.get(ArchiveDocument, "emb2")
    assert doc is not None
    doc.scope_content = "texto novo escrito pelo arquivista"
    doc.review_status = ArchiveReviewStatus.HUMAN_APPROVED
    db_session.commit()

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    engine.embed.assert_called_once()
    db_session.expire_all()
    assert db_session.get(ArchiveDocument, "emb2").review_status == ArchiveReviewStatus.HUMAN_APPROVED


def test_worker_skips_rejected_documents(use_test_db, db_session, mock_registry, generate_archive_doc):
    generate_archive_doc(
        description_id="rejected", original_title="Descartado", review_status=ArchiveReviewStatus.REJECTED
    )
    engine = _fake_engine(mock_registry)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    engine.embed.assert_not_called()
    db_session.expire_all()
    assert db_session.get(ArchiveDocument, "rejected").embedding is None


def test_worker_stamps_a_document_without_text_without_embedding(
    use_test_db, db_session, mock_registry, generate_archive_doc
):
    """An empty document leaves the queue instead of being retried forever."""
    generate_archive_doc(description_id="empty", original_title="")
    engine = _fake_engine(mock_registry)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    engine.embed.assert_not_called()
    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, "empty")
    assert stored.embedding is None
    assert "worker_embedding_v1" in stored.execution_log


def test_worker_force_reembeds_everything(use_test_db, db_session, mock_registry, generate_archive_doc):
    generate_archive_doc(description_id="force1", original_title="Já embedado")
    engine = _fake_engine(mock_registry)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore
    engine.embed.reset_mock()

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", force=True)  # type: ignore

    engine.embed.assert_called_once()


def test_worker_respects_the_batch_size(use_test_db, db_session, mock_registry, generate_archive_doc):
    for index in range(3):
        generate_archive_doc(description_id=f"batch{index}", original_title=f"Documento {index}")
    engine = _fake_engine(mock_registry)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste", db_batch_size=2)  # type: ignore

    # 3 documents with a batch of 2 mean two round trips to the model.
    assert engine.embed.call_count == 2


def test_worker_rolls_back_when_the_engine_fails(use_test_db, db_session, mock_registry, generate_archive_doc):
    generate_archive_doc(description_id="boom", original_title="Falha de memória")
    MockClass = mock_registry(embeddings_registry)
    MockClass.return_value.embed.side_effect = RuntimeError("out of memory")

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    db_session.expire_all()
    stored = db_session.get(ArchiveDocument, "boom")
    assert stored.embedding is None
    assert "worker_embedding_v1" not in (stored.execution_log or {})


def test_worker_passes_the_composed_text_to_the_engine(use_test_db, db_session, mock_registry, generate_archive_doc):
    """Title first, then the body; empty columns are not sent."""
    generate_archive_doc(
        description_id="text1",
        original_title="Título original",
        final_title="Título final",
        scope_content="Escopo",
        provenance=None,
    )
    engine = _fake_engine(mock_registry)

    execute(db=db_session, engine_name="motor_fake", preset="preset_teste")  # type: ignore

    texts = engine.embed.call_args.args[0]
    assert texts == ["Título final\nEscopo"]
