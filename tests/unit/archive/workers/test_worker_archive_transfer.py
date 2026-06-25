from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from domains.archive.schemas.document_schema import ArchiveDocumentDTO
from domains.archive.workers import worker_archive_transfer

# ==========================================
# TESTES DE ORQUESTRAÇÃO E TRANSAÇÃO (Worker ETL)
# ==========================================


def test_run_archive_transfer_fluxo_completo(mocker: MockerFixture, mock_staging_doc) -> None:
    """Testa o caminho feliz: Doc inédito, extração de tags e vinculação em Bulk."""
    mock_db = mocker.Mock(spec=Session)

    # Intercepta as conexões de banco global (get_db)
    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Cria o documento Mock via factory
    doc_staging = mock_staging_doc(description_id="doc-100", raw_content_hash="hash_123")

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_staging]

    # 1. MOCK DAS CLASSES QUE O WORKER INSTANCIA LÁ DENTRO
    mock_doc_repo_class = mocker.patch("domains.archive.workers.worker_archive_transfer.DocumentRepository")
    mock_tag_repo_class = mocker.patch("domains.archive.workers.worker_archive_transfer.TagRepository")
    mock_tag_service_class = mocker.patch("domains.archive.workers.worker_archive_transfer.TagService")

    # 2. CONFIGURANDO AS RESPOSTAS DAS INSTÂNCIAS
    mock_doc_repo = mock_doc_repo_class.return_value
    mock_tag_repo = mock_tag_repo_class.return_value
    mock_tag_service = mock_tag_service_class.return_value

    mock_doc_repo.upsert_archive_document.return_value = True
    mock_tag_service.extract_and_clean_tags.return_value = [mocker.Mock()]
    mock_tag_service.process_worker_tags.return_value = [99, 100]  # Retorna duas tags para vincular

    # 3. EXECUTA O WORKER
    worker_archive_transfer.execute(mock_db)

    # 4. VALIDAÇÕES: Upsert de Documentos
    assert mock_doc_repo.upsert_archive_document.call_count == 1
    args, _ = mock_doc_repo.upsert_archive_document.call_args
    dto_enviado: ArchiveDocumentDTO = args[0]  # Pega o primeiro argumento enviado

    assert dto_enviado.description_id == "doc-100"
    assert dto_enviado.staging_content_hash == "hash_123"
    assert dto_enviado.execution_log == {}

    # 5. VALIDAÇÕES: Chamadas de Regra de Negócio (TagService)
    mock_tag_service.extract_and_clean_tags.assert_called_once()
    mock_tag_service.process_worker_tags.assert_called_once()

    # 6. VALIDAÇÕES: Otimização de Banco (Bulk Insert no Buffer)
    # Garante que o Worker montou o dicionário corretamente antes de enviar pro repo
    mock_tag_repo.bulk_link_tags.assert_called_once_with(
        [{"description_id": "doc-100", "tag_id": 99}, {"description_id": "doc-100", "tag_id": 100}]
    )

    # O loop terminou, então deve comitar a transação final
    mock_db.commit.assert_called_once()


def test_run_archive_transfer_idempotencia(mocker: MockerFixture, mock_staging_doc) -> None:
    """Testa a Carga Incremental: Se o Hash for igual, o Upsert retorna False e o pipeline pula o processamento."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    doc_staging = mock_staging_doc()

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_staging]

    # Mocks
    mock_doc_repo_class = mocker.patch("domains.archive.workers.worker_archive_transfer.DocumentRepository")
    mock_tag_repo_class = mocker.patch("domains.archive.workers.worker_archive_transfer.TagRepository")
    mock_tag_service_class = mocker.patch("domains.archive.workers.worker_archive_transfer.TagService")

    mock_doc_repo = mock_doc_repo_class.return_value
    mock_tag_repo = mock_tag_repo_class.return_value
    mock_tag_service = mock_tag_service_class.return_value

    # Simulamos o bloqueio no upsert (O Documento já existia e não sofreu alterações na Staging)
    mock_doc_repo.upsert_archive_document.return_value = False

    # Executa
    worker_archive_transfer.execute(mock_db)

    # Validações
    mock_doc_repo.upsert_archive_document.assert_called_once()

    # Como não houve insert/update, ele não deve processar Tags
    mock_tag_service.extract_and_clean_tags.assert_not_called()
    mock_tag_service.process_worker_tags.assert_not_called()
    mock_tag_repo.bulk_link_tags.assert_not_called()

    mock_db.commit.assert_called_once()


def test_run_archive_transfer_resiliencia_em_lote(mocker: MockerFixture, mock_staging_doc) -> None:
    """Garante que se um documento explodir (Exception), o Worker anota a falha e continua processando os outros."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Cria DOIS documentos na fila
    doc_falha = mock_staging_doc(description_id="doc-falha")
    doc_sucesso = mock_staging_doc(description_id="doc-sucesso")

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [doc_falha, doc_sucesso]

    # Mocks
    mock_doc_repo_class = mocker.patch("domains.archive.workers.worker_archive_transfer.DocumentRepository")
    mock_tag_repo_class = mocker.patch("domains.archive.workers.worker_archive_transfer.TagRepository")
    mock_tag_service_class = mocker.patch("domains.archive.workers.worker_archive_transfer.TagService")

    mock_doc_repo = mock_doc_repo_class.return_value
    mock_tag_repo = mock_tag_repo_class.return_value
    mock_tag_service = mock_tag_service_class.return_value

    # Força o primeiro Upsert a explodir com um erro grave e o segundo a funcionar
    mock_doc_repo.upsert_archive_document.side_effect = [Exception("Erro Fatal PostgreSQL"), True]

    mock_tag_service.extract_and_clean_tags.return_value = []
    mock_tag_service.process_worker_tags.return_value = [10]

    # Executa
    worker_archive_transfer.execute(mock_db)

    # O Upsert deve ter sido chamado 2 vezes (não parou no primeiro erro!)
    assert mock_doc_repo.upsert_archive_document.call_count == 2

    # O buffer de envio em massa deve ter salvo apenas os vínculos do SEGUNDO documento (que sobreviveu)
    mock_tag_repo.bulk_link_tags.assert_called_once_with([{"description_id": "doc-sucesso", "tag_id": 10}])
