from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from scrinalia.domains.archive.ports.staging_source import StagingRecord
from scrinalia.domains.archive.schemas.command_schema import TagLinkCommand
from scrinalia.domains.archive.schemas.document_schema import ArchiveDocumentDTO
from scrinalia.domains.archive.workers import worker_archive_transfer

# ==========================================
# ORCHESTRATION AND TRANSACTION TESTS (ETL Worker)
# ==========================================


def _patch_level_catalog(mocker: MockerFixture, index: dict[str, int] | None = None):
    """
    Shields the level catalogue, exactly as ``mock_registry`` shields the AI engines.

    The transfer resolves the declared level through the catalogue, and these tests mock the
    session, so the catalogue has to be patched too: without it the repository would read from a
    ``Mock``. An empty index is a catalogue that knows nothing, which is the honest default here —
    the spelling itself is covered by the unit tests of ``domain.level_catalog``.
    """
    repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.LevelCatalogRepository")
    repo_class.return_value.level_index.return_value = index or {}
    return repo_class


def test_run_archive_transfer_full_flow(mocker: MockerFixture, mock_staging_doc) -> None:
    """Tests the happy path: New doc, tag extraction and bulk linking."""
    _patch_level_catalog(mocker, {"dossie": 5})
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
    mock_doc_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.DocumentRepository")
    mock_tag_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.TagRepository")
    mock_tag_service_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.TagService")

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
    # The CDC key is the hash of the parsed record, not of the raw payload.
    assert sent_dto.staging_content_hash == StagingRecord.model_validate(staging_doc).parsed_content_hash()
    assert sent_dto.execution_log == {}
    # The declared text was resolved against the catalogue on the way in, not stored as text.
    assert sent_dto.level_id == 5
    # The double declares no parent, so the payload says nothing about the arrangement: omitting it
    # is what lets the upsert leave a curated tree exactly where it is.
    assert sent_dto.parent_id is None
    assert sent_dto.path is None

    # 5. VALIDATIONS: Business Rule Calls (TagService)
    mock_tag_service.extract_and_clean_tags.assert_called_once()
    mock_tag_service.process_worker_tags.assert_called_once()

    # 6. VALIDATIONS: Database Optimization (Bulk Insert in the Buffer)
    # Guarantees that the Worker built the dictionary correctly before sending it to the repo
    mock_tag_repo.bulk_link_tags.assert_called_once_with(
        [TagLinkCommand(description_id="doc-100", tag_id=99), TagLinkCommand(description_id="doc-100", tag_id=100)]
    )

    # The loop finished: one commit for the batch and one for the late-parent retry pass.
    assert mock_db.commit.call_count == 2


def test_run_archive_transfer_consumes_ports_without_staging_orm(mocker: MockerFixture) -> None:
    """The transfer use case must read staging through the port, not the staging ORM."""
    from scrinalia.domains.archive.ports.staging_source import StagingRecord

    _patch_level_catalog(mocker, {"dossie": 5})
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

    mock_doc_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.DocumentRepository")
    mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.TagRepository")
    mock_tag_service_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.TagService")

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
    _patch_level_catalog(mocker, {"dossie": 5})
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_archive_transfer, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db
    mock_db.begin_nested.return_value = mocker.MagicMock()

    staging_doc = mock_staging_doc()

    mock_query = mocker.Mock()
    mock_db.scalars.return_value = mock_query
    mock_query.yield_per.return_value = [staging_doc]

    # Mocks
    mock_doc_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.DocumentRepository")
    mock_tag_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.TagRepository")
    mock_tag_service_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.TagService")

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

    assert mock_db.commit.call_count == 2


def test_run_archive_transfer_batch_resilience(mocker: MockerFixture, mock_staging_doc) -> None:
    """Guarantees that if a document explodes (Exception), the Worker records the failure and keeps processing the others."""
    _patch_level_catalog(mocker, {"dossie": 5})
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
    mock_doc_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.DocumentRepository")
    mock_tag_repo_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.TagRepository")
    mock_tag_service_class = mocker.patch("scrinalia.domains.archive.workers.worker_archive_transfer.TagService")

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
