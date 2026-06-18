from unittest.mock import patch

from domains.archive.models import ArchiveDocument
from domains.archive.workers.worker_typology import execute


def test_worker_integracao_atualiza_banco_corretamente(
    use_test_db,
    db_session,
    generate_archive_doc,
    generate_typology,
    mock_registry_typology,
):
    # 1. Preparação Real no Banco
    tipo_real = generate_typology(id=99, name="dossiê")
    doc_real = generate_archive_doc(original_title="Dossiê do Servidor João", scope_content="Documentos admissionais.")

    doc_id = doc_real.description_id
    expected_typology_id = tipo_real.typology_id

    # 2. Prepara a IA Falsa
    instancia_da_ia = mock_registry_typology.return_value
    instancia_da_ia.classify.return_value = [{"labels": [tipo_real.name], "scores": [0.85]}]

    # 3. Ação: Passamos o db_session isolado do Pytest direto para o worker!
    execute(
        db=db_session,  # <--- Injeção limpa no teste
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )

    # 4. Verificações (Asserts)

    doc_atualizado = db_session.get(ArchiveDocument, doc_id)

    assert doc_atualizado.typology_id == expected_typology_id
    assert doc_atualizado.execution_log["worker_typology_classifier_v1"] == "DONE"


def test_worker_sai_graciosamente_sem_tipologias_cadastradas(db_session, mock_registry_typology):
    # O banco está vazio (nenhuma tipologia criada)
    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    # O teste passa simplesmente se a função executar até o fim sem levantar exceções.
    # O log "Nenhuma tipologia cadastrada" será emitido internamente.
    instancia_da_ia = mock_registry_typology.return_value
    instancia_da_ia.classify.assert_not_called()


def test_worker_sai_graciosamente_sem_documentos_pendentes(
    db_session, generate_typology, generate_archive_doc, mock_registry_typology
):
    generate_typology(id=1, name="Dossiê")

    # Criamos um documento que JÁ FOI processado por essa versão do worker
    generate_archive_doc(execution_log={"worker_typology_classifier_v1": "DONE"})

    instancia_da_ia = mock_registry_typology.return_value

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    # A IA não deve ser acionada, pois o Where do banco filtrou o documento
    instancia_da_ia.classify.assert_not_called()


def test_worker_ignora_documentos_vazios_e_carimba_done(
    db_session, generate_typology, generate_archive_doc, mock_registry_typology
):
    generate_typology(id=1, name="Dossiê")

    # Documento sem texto útil (Nulo em uma coluna e vazio na outra)
    doc = generate_archive_doc(original_title="", scope_content="   ")
    doc_id = doc.description_id

    instancia_da_ia = mock_registry_typology.return_value

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
        columns_to_classify=["original_title", "scope_content"],
    )

    # A IA não pode receber strings vazias
    instancia_da_ia.classify.assert_not_called()

    # Mas o documento DEVE ser carimbado para não entrar em loop na próxima rodada
    doc_atualizado = db_session.get(ArchiveDocument, doc_id)
    assert doc_atualizado.typology_id is None
    assert doc_atualizado.execution_log["worker_typology_classifier_v1"] == "DONE"


def test_worker_ignora_baixa_confianca_da_ia(
    db_session, generate_typology, generate_archive_doc, mock_registry_typology
):
    tipo = generate_typology(id=1, name="Dossiê")
    doc = generate_archive_doc(original_title="Texto confuso sem contexto")
    doc_id = doc.description_id

    instancia_da_ia = mock_registry_typology.return_value

    # IA devolve apenas 30% de confiança (seu limiar é 40%)
    instancia_da_ia.classify.return_value = [{"labels": [tipo.name], "scores": [0.30]}]

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    doc_atualizado = db_session.get(ArchiveDocument, doc_id)

    # Não deve arquivar
    assert doc_atualizado.typology_id is None
    # Deve carimbar como feito
    assert doc_atualizado.execution_log["worker_typology_classifier_v1"] == "DONE"


def test_worker_lida_com_alucinacao_da_ia(db_session, generate_typology, generate_archive_doc, mock_registry_typology):
    generate_typology(id=1, name="Dossiê")
    doc = generate_archive_doc(original_title="Documento normal")
    doc_id = doc.description_id

    instancia_da_ia = mock_registry_typology.return_value

    # IA devolve uma label inventada que não existe no mapa do banco
    instancia_da_ia.classify.return_value = [{"labels": ["Tipologia Inexistente"], "scores": [0.99]}]

    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    doc_atualizado = db_session.get(ArchiveDocument, doc_id)

    # Não pode quebrar com KeyError, deve manter nulo
    assert doc_atualizado.typology_id is None
    assert doc_atualizado.execution_log["worker_typology_classifier_v1"] == "DONE"


def test_worker_faz_rollback_em_falha_da_ia(
    db_session, generate_typology, generate_archive_doc, mock_registry_typology
):
    generate_typology(id=1, name="Dossiê")
    doc = generate_archive_doc(original_title="Texto gigante")
    doc_id = doc.description_id

    instancia_da_ia = mock_registry_typology.return_value

    # Simulamos o modelo da HuggingFace estourando a memória (OOM)
    instancia_da_ia.classify.side_effect = Exception("CUDA Out of Memory")

    # O worker deve capturar o erro internamente e dar break no loop de forma segura
    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore
        preset="preset_teste",  # type: ignore
    )

    doc_atualizado = db_session.get(ArchiveDocument, doc_id)

    # Como ocorreu rollback e break na hora do processamento da IA, o documento
    # deve continuar intocado no banco (sem carimbo) para ser tentado novamente depois.
    assert doc_atualizado.typology_id is None
    assert doc_atualizado.execution_log is None or "worker_typology_classifier_v1" not in doc_atualizado.execution_log


def test_worker_faz_rollback_em_falha_de_commit(
    db_session, generate_typology, generate_archive_doc, mock_registry_typology
):
    tipo = generate_typology(id=1, name="Dossiê")
    doc = generate_archive_doc(original_title="Documento perfeito")
    doc_id = doc.description_id

    instancia_da_ia = mock_registry_typology.return_value
    instancia_da_ia.classify.return_value = [{"labels": [tipo.name], "scores": [0.90]}]

    # Usamos o patch.object para interceptar EXATAMENTE o método commit da nossa sessão atual
    with patch.object(db_session, "commit", side_effect=Exception("Conexão com PostgreSQL perdida")):
        # O worker vai classificar, carimbar na memória e tentar commitar, mas vai estourar erro
        execute(
            db=db_session,
            engine_name="motor_fake",  # type: ignore
            preset="preset_teste",  # type: ignore
        )

    # O rollback do seu worker entra em ação. O documento volta ao estado original.
    doc_atualizado = db_session.get(ArchiveDocument, doc_id)

    assert doc_atualizado.typology_id is None
    assert doc_atualizado.execution_log is None or "worker_typology_classifier_v1" not in doc_atualizado.execution_log
