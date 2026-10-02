from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from memoria_curitibana.domains.archive.schemas.command_schema import TagLinkCommand
from memoria_curitibana.domains.archive.schemas.document_schema import ArchiveDocumentDTO
from memoria_curitibana.domains.archive.workers import worker_archive_transfer

# ==========================================
# ORCHESTRATION AND TRANSACTION TESTS (ETL Worker)
# ==========================================


def test_run_archive_transfer_full_flow(mocker: MockerFixture, mock_staging_doc) -> None:
    """Tests the happy path: New doc, tag extraction and bulk linking."""
    mock_db = mocker.Mock(spec=Session)

    # Intercepts the global database connections (get_db)
    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Creates the Mock document via factory
    staging_doc = mock_staging_doc(description_id="doc-100", raw_content_hash="hash_123")

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [staging_doc]

    # 1. MOCK OF THE CLASSES THE WORKER INSTANTIATES INSIDE
    mock_doc_repo_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.DocumentRepository"
    )
    mock_tag_repo_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.TagRepository"
    )
    mock_tag_service_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.TagService"
    )

    # 2. CONFIGURING THE INSTANCE RESPONSES
    mock_doc_repo = mock_doc_repo_class.return_value
    mock_tag_repo = mock_tag_repo_class.return_value
    mock_tag_service = mock_tag_service_class.return_value

    mock_doc_repo.upsert_archive_document.return_value = True
    mock_tag_service.extract_and_clean_tags.return_value = [mocker.Mock()]
    mock_tag_service.process_worker_tags.return_value = [99, 100]  # Returns two tags to link

    # 3. RUN THE WORKER
    worker_archive_transfer.execute(mock_db)

    # 4. VALIDATIONS: Document Upsert
    assert mock_doc_repo.upsert_archive_document.call_count == 1
    args, _ = mock_doc_repo.upsert_archive_document.call_args
    sent_dto: ArchiveDocumentDTO = args[0]  # Takes the first argument sent

    assert sent_dto.description_id == "doc-100"
    assert sent_dto.staging_content_hash == "hash_123"
    assert sent_dto.execution_log == {}

    # 5. VALIDATIONS: Business Rule Calls (TagService)
    mock_tag_service.extract_and_clean_tags.assert_called_once()
    mock_tag_service.process_worker_tags.assert_called_once()

    # 6. VALIDATIONS: Database Optimization (Bulk Insert in the Buffer)
    # Guarantees that the Worker built the dictionary correctly before sending it to the repo
    mock_tag_repo.bulk_link_tags.assert_called_once_with(
        [TagLinkCommand(description_id="doc-100", tag_id=99), TagLinkCommand(description_id="doc-100", tag_id=100)]
    )

    # The loop finished, so it must commit the final transaction
    mock_db.commit.assert_called_once()


def test_run_archive_transfer_consumes_ports_without_staging_orm(mocker: MockerFixture) -> None:
    """The transfer use case must read staging through the port, not the staging ORM."""
    from memoria_curitibana.domains.archive.ports.staging_source import StagingRecord

    mock_db = mocker.Mock(spec=Session)
    mock_db.begin_nested.return_value = mocker.MagicMock()

    record = StagingRecord(
        description_id="doc-port",
        title="Dossiê via porta",
        raw_content_hash="hash_port",
        indexing_points="Urbanismo",
    )
    source = mocker.Mock()
    source.stream.return_value = iter([record])

    mock_doc_repo_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.DocumentRepository"
    )
    mocker.patch("memoria_curitibana.domains.archive.workers.worker_archive_transfer.TagRepository")
    mock_tag_service_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.TagService"
    )

    mock_doc_repo = mock_doc_repo_class.return_value
    mock_doc_repo.upsert_archive_document.return_value = True

    mock_tag_service = mock_tag_service_class.return_value
    mock_tag_service.extract_and_clean_tags.return_value = []
    mock_tag_service.process_worker_tags.return_value = []

    worker_archive_transfer.execute(mock_db, source=source)

    source.stream.assert_called_once()
    args, _ = mock_doc_repo.upsert_archive_document.call_args
    sent_dto: ArchiveDocumentDTO = args[0]
    assert sent_dto.description_id == "doc-port"
    assert sent_dto.original_title == "Dossiê via porta"


def test_run_archive_transfer_idempotency(mocker: MockerFixture, mock_staging_doc) -> None:
    """Tests Incremental Loading: If the Hash is equal, the Upsert returns False and the pipeline skips processing."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    staging_doc = mock_staging_doc()

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [staging_doc]

    # Mocks
    mock_doc_repo_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.DocumentRepository"
    )
    mock_tag_repo_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.TagRepository"
    )
    mock_tag_service_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.TagService"
    )

    mock_doc_repo = mock_doc_repo_class.return_value
    mock_tag_repo = mock_tag_repo_class.return_value
    mock_tag_service = mock_tag_service_class.return_value

    # Simulate the upsert block (the Document already existed and did not change in Staging)
    mock_doc_repo.upsert_archive_document.return_value = False

    # Run
    worker_archive_transfer.execute(mock_db)

    # Validations
    mock_doc_repo.upsert_archive_document.assert_called_once()

    # Since there was no insert/update, it must not process Tags
    mock_tag_service.extract_and_clean_tags.assert_not_called()
    mock_tag_service.process_worker_tags.assert_not_called()
    mock_tag_repo.bulk_link_tags.assert_not_called()

    mock_db.commit.assert_called_once()


def test_run_archive_transfer_batch_resilience(mocker: MockerFixture, mock_staging_doc) -> None:
    """Guarantees that if a document explodes (Exception), the Worker records the failure and keeps processing the others."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Creates TWO documents in the queue
    failing_doc = mock_staging_doc(description_id="doc-falha")
    success_doc = mock_staging_doc(description_id="doc-sucesso")

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [failing_doc, success_doc]

    # Mocks
    mock_doc_repo_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.DocumentRepository"
    )
    mock_tag_repo_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.TagRepository"
    )
    mock_tag_service_class = mocker.patch(
        "memoria_curitibana.domains.archive.workers.worker_archive_transfer.TagService"
    )

    mock_doc_repo = mock_doc_repo_class.return_value
    mock_tag_repo = mock_tag_repo_class.return_value
    mock_tag_service = mock_tag_service_class.return_value

    # Forces the first Upsert to explode with a serious error and the second to work
    mock_doc_repo.upsert_archive_document.side_effect = [Exception("Erro Fatal PostgreSQL"), True]

    mock_tag_service.extract_and_clean_tags.return_value = []
    mock_tag_service.process_worker_tags.return_value = [10]

    # Run
    worker_archive_transfer.execute(mock_db)

    # The Upsert must have been called 2 times (it did not stop on the first error!)
    assert mock_doc_repo.upsert_archive_document.call_count == 2

    # The bulk send buffer must have saved only the links from the SECOND document (which survived)
    mock_tag_repo.bulk_link_tags.assert_called_once_with([TagLinkCommand(description_id="doc-sucesso", tag_id=10)])
