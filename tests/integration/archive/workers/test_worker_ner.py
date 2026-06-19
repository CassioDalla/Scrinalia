from unittest.mock import patch

from domains.archive.workers.worker_ner import execute


@patch("domains.archive.workers.worker_ner.get_engine")
@patch("domains.archive.workers.worker_ner.repository.get_or_create_entities")
@patch("domains.archive.workers.worker_ner.repository.link_description_relationships")
def test_worker_ner_integracao_banco_real(
    mock_link,
    mock_get_or_create,
    mock_get_engine,
    mock_ner_engine,
    db_session,  # A sua sessão PostgreSQL injetada!
    generate_archive_doc,  # A sua fábrica de documentos
):
    """Integração: Testa o SQL real de UPDATE e a manipulação do campo JSONB."""

    mock_get_engine.return_value = mock_ner_engine
    mock_get_or_create.return_value = [999]
    mock_link.return_value = None

    # 1. Inserimos um documento real no PostgreSQL
    doc_real = generate_archive_doc(
        original_title="Relatório Anual", scope_content="Documento emitido pela Sec. de Finanças."
    )

    doc_id_salvo = str(doc_real.description_id)
    # 2. O Worker roda usando a sessão real
    execute(db=db_session)

    # 3. Verificações no Banco de Dados
    db_session.expire_all()  # Limpa o cache para forçar a leitura do banco
    doc_atualizado = db_session.get(type(doc_real), doc_id_salvo)

    # Verifica se o JSONB foi gravado perfeitamente no disco
    assert doc_atualizado.execution_log is not None
    assert doc_atualizado.execution_log["worker_ner_v1"] == "DONE"

    # Confirma o envio do texto para a IA
    args, _ = mock_ner_engine.extract.call_args
    assert args[0] == ["Relatório Anual. Documento emitido pela Sec. de Finanças."]


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integracao_ignora_documentos_ja_processados(
    mock_get_engine, mock_ner_engine, db_session, generate_archive_doc
):
    """Integração: Valida se a query WHERE do SQLAlchemy respeita o JSONB do PostgreSQL."""
    mock_get_engine.return_value = mock_ner_engine

    # Inserimos um documento no banco real que JÁ POSSUI o carimbo
    doc_velho = generate_archive_doc(
        original_title="Documento Antigo", execution_log={"worker_ner_v1": "DONE", "algum_outro_worker": "ERROR"}
    )

    # Executa o orquestrador
    execute(db=db_session)

    # Verifica se a IA foi completamente ignorada, pois a query do banco deve ter retornado vazia
    mock_ner_engine.extract.assert_not_called()


@patch("domains.archive.workers.worker_ner.get_engine")
@patch("domains.archive.workers.worker_ner.repository.get_or_create_entities")
@patch("domains.archive.workers.worker_ner.repository.link_description_relationships")
def test_worker_ner_integracao_processa_multiplos_lotes(
    mock_link, mock_get_or_create, mock_get_engine, mock_ner_engine, db_session, generate_archive_doc
):
    """Integração: Valida se o while True avança corretamente pelas páginas de paginação no DB."""
    mock_get_engine.return_value = mock_ner_engine
    mock_get_or_create.return_value = [99]
    mock_link.return_value = None

    # Criamos 3 documentos no banco
    doc1 = generate_archive_doc(description_id="doc-1", original_title="Texto 1")
    doc2 = generate_archive_doc(description_id="doc-2", original_title="Texto 2")
    doc3 = generate_archive_doc(description_id="doc-3", original_title="Texto 3")

    # Executamos forçando um batch_size minúsculo de 2
    # Isso forçará o worker a dar 2 voltas no laço while (Lote 1 com 2 docs, Lote 2 com 1 doc)
    execute(db=db_session, db_batch_size=2)

    db_session.expire_all()

    # Todos os 3 documentos precisam ter o carimbo DONE salvo no banco
    assert db_session.get(type(doc1), "doc-1").execution_log["worker_ner_v1"] == "DONE"
    assert db_session.get(type(doc2), "doc-2").execution_log["worker_ner_v1"] == "DONE"
    assert db_session.get(type(doc3), "doc-3").execution_log["worker_ner_v1"] == "DONE"

    # A inferência da IA (o extract em lote) deve ter sido chamada exatamente 2 vezes
    assert mock_ner_engine.extract.call_count == 2


@patch("domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integracao_ignora_linhas_100_nulas(
    mock_get_engine, mock_ner_engine, db_session, generate_archive_doc
):
    """Integração: Valida o or_() do SQLAlchemy. Docs sem campos textuais não entram na fila."""
    mock_get_engine.return_value = mock_ner_engine

    # Documento com TODOS os campos textuais de NER nulos
    doc_fantasma = generate_archive_doc(
        original_title="Titulo teste doc", admin_bio_history=None, provenance=None, scope_content=None
    )

    doc_id_salvo = str(doc_fantasma.description_id)
    execute(db=db_session, columns_to_extract=["scope_content", "admin_bio_history"])

    # A query do banco deve ignorar essa linha sumariamente
    mock_ner_engine.extract.assert_not_called()

    # O documento no banco deve continuar intocado (sem execution_log criado pelo Worker)
    db_session.expire_all()
    doc_verificado = db_session.get(type(doc_fantasma), doc_fantasma.description_id)
    assert doc_verificado.execution_log is None or "worker_ner_v1" not in doc_verificado.execution_log
