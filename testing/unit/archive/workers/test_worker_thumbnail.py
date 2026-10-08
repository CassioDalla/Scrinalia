from pytest_mock import MockerFixture
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from scrinalia.domains.archive.workers import worker_thumbnail

# ==========================================
# 1. NETWORK AND MEMORY TESTS
# ==========================================


def test_download_image_to_memory_success(mocker: MockerFixture) -> None:
    """Tests the download by simulating a 200 HTTP response and PIL processing."""
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.content = b"fake_bytes"

    mocker.patch("requests.get", return_value=mock_response)

    # Pretend that PIL opened the image successfully
    mock_image = mocker.Mock()
    mock_image.mode = "RGB"
    mocker.patch("PIL.Image.open", return_value=mock_image)

    result = worker_thumbnail.download_image_to_memory("http://site.com/img.png")

    assert result is not None
    # Checks whether the image was saved into the output buffer
    mock_image.save.assert_called_once()


def test_download_image_to_memory_http_failure(mocker: MockerFixture) -> None:
    """Guarantees that 404/500 errors from the city hall do not break the worker."""
    mock_response = mocker.Mock()
    mock_response.status_code = 404
    mocker.patch("requests.get", return_value=mock_response)

    result = worker_thumbnail.download_image_to_memory("http://site.com/img.png")

    assert result is None


def test_download_image_to_memory_exception(mocker: MockerFixture) -> None:
    """Guarantees that network drops (Timeout) are handled gracefully."""
    mocker.patch("requests.get", side_effect=Exception("Connection Timeout"))

    result = worker_thumbnail.download_image_to_memory("http://site.com/img.png")

    assert result is None


# ==========================================
# 2. ORCHESTRATION TESTS
# ==========================================


def test_execute_worker_thumbnails_success(mocker: MockerFixture) -> None:
    """Happy path: Downloads the image, uploads it to Storage and saves the URI."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_thumbnail, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db

    # FIX: MagicMock
    mock_db.begin_nested.return_value = mocker.MagicMock()

    # Creates a pending fake document
    fake_doc = mocker.Mock()
    fake_doc.description_id = "doc-1"
    fake_doc.original_thumbnail_url = "http://link.com"
    fake_doc.storage_thumbnail_uri = None
    fake_doc.execution_log = {}

    mock_db.scalars.return_value.yield_per.return_value = [fake_doc]

    # Mocks of external integrations (network and S3)
    mocker.patch.object(worker_thumbnail, "download_image_to_memory", return_value=b"bytes")

    mock_storage = mocker.patch("scrinalia.domains.archive.workers.worker_thumbnail.S3Storage")
    mock_storage.return_value.upload_file.return_value = "s3://bucket/thumb_doc-1.jpg"

    # Prevents the sleep from slowing down the tests
    mocker.patch("time.sleep")

    worker_thumbnail.execute(mock_db)

    # Validations
    assert fake_doc.storage_thumbnail_uri == "s3://bucket/thumb_doc-1.jpg"
    mock_storage.return_value.upload_file.assert_called_once()
    mock_db.commit.assert_called_once()


def test_execute_worker_thumbnails_marks_failure_in_json(mocker: MockerFixture) -> None:
    """If the download fails, the worker must mark the failure in execution_log."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_thumbnail, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db

    # FIX: MagicMock
    mock_db.begin_nested.return_value = mocker.MagicMock()

    fake_doc = mocker.Mock()
    fake_doc.original_thumbnail_url = "http://link-quebrado.com"
    fake_doc.execution_log = {}

    mock_db.scalars.return_value.yield_per.return_value = [fake_doc]

    # Forces the download to fail
    mocker.patch.object(worker_thumbnail, "download_image_to_memory", return_value=None)
    mock_flag = mocker.patch("scrinalia.domains.archive.workers.worker_thumbnail.flag_modified")
    mocker.patch("time.sleep")

    worker_thumbnail.execute(mock_db)

    # The document does not receive the URI, but receives the failure flag
    assert fake_doc.execution_log == {"thumbnail_failed": "True"}
    mock_flag.assert_called_once_with(fake_doc, "execution_log")
    mock_db.commit.assert_called_once()


def test_execute_worker_thumbnails_stamps_unexpected_exceptions(mocker: MockerFixture) -> None:
    """Regression: an unexpected error must also stamp the document, else it retries forever."""
    mock_db = mocker.Mock(spec=Session)

    mock_get_db = mocker.patch.object(worker_thumbnail, "get_db")
    mock_get_db.return_value.__enter__.return_value = mock_db

    mock_db.begin_nested.return_value = mocker.MagicMock()

    fake_doc = mocker.Mock()
    fake_doc.description_id = "doc-boom"
    fake_doc.original_thumbnail_url = "http://link.com"
    fake_doc.execution_log = {}

    mock_db.scalars.return_value.yield_per.return_value = [fake_doc]

    # The download helper itself explodes (not returns None), forcing the outer except.
    mocker.patch.object(worker_thumbnail, "download_image_to_memory", side_effect=Exception("boom"))
    mock_flag = mocker.patch("scrinalia.domains.archive.workers.worker_thumbnail.flag_modified")
    mocker.patch("time.sleep")

    worker_thumbnail.execute(mock_db)

    assert fake_doc.execution_log == {"thumbnail_failed": "True"}
    mock_flag.assert_called_once_with(fake_doc, "execution_log")


def test_execute_worker_uses_injected_storage_port(mocker: MockerFixture) -> None:
    """The worker must accept any ThumbnailStoragePort instead of building S3Storage itself."""
    mock_db = mocker.Mock(spec=Session)
    mock_db.begin_nested.return_value = mocker.MagicMock()

    fake_doc = mocker.Mock()
    fake_doc.description_id = "doc-port"
    fake_doc.original_thumbnail_url = "http://link.com"
    fake_doc.storage_thumbnail_uri = None
    fake_doc.execution_log = {}
    mock_db.scalars.return_value.yield_per.return_value = [fake_doc]

    mocker.patch.object(worker_thumbnail, "download_image_to_memory", return_value=b"bytes")
    mock_s3_cls = mocker.patch("scrinalia.domains.archive.workers.worker_thumbnail.S3Storage")
    mocker.patch("time.sleep")

    fake_storage = mocker.Mock()
    fake_storage.upload_file.return_value = "s3://bucket/thumb_doc-port.jpg"

    worker_thumbnail.execute(mock_db, storage=fake_storage)

    fake_storage.upload_file.assert_called_once()
    mock_s3_cls.assert_not_called()
    assert fake_doc.storage_thumbnail_uri == "s3://bucket/thumb_doc-port.jpg"


# ==========================================
# 3. THE FAILURE MARK AND THE WAY BACK
# ==========================================


def _sql(conditions) -> str:
    """The predicate as SQL with its literals inlined, so the keys are readable."""
    dialect = postgresql.dialect()
    return " AND ".join(
        str(condition.compile(dialect=dialect, compile_kwargs={"literal_binds": True})) for condition in conditions
    )


def test_pending_conditions_exclude_the_failed_documents() -> None:
    """A dead link must not loop forever, so the plain run skips what is already marked."""
    assert "thumbnail_failed" in _sql(worker_thumbnail.pending_conditions())


def test_force_brings_the_failed_documents_back() -> None:
    """``force`` is the way back from a mark a transient outage left behind.

    Without it, an afternoon with the bucket down was indistinguishable from a broken link and
    those documents never returned to the queue.
    """
    forced = worker_thumbnail.pending_conditions(force=True)

    assert "thumbnail_failed" not in _sql(forced)
    assert len(forced) == len(worker_thumbnail.pending_conditions()) - 1
