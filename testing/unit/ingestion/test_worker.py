import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from scrinalia.domains.ingestion import repository, worker
from scrinalia.domains.ingestion.models import ScrapeStatus, ScrapingQueue
from scrinalia.domains.ingestion.ports import (
    AdapterFatalError,
    AdapterNetworkError,
    AdapterNotFoundError,
    IDetailAdapter,
)

# ==========================================
# INGESTION ORCHESTRATOR TESTS (WORKER)
# ==========================================


@pytest.fixture(autouse=True)
def _stub_the_remaining_count(mocker: MockerFixture) -> None:
    """
    Every run ends by reporting how much is left, through the repository's own counter.

    These tests are about the orchestration, so the count is stubbed here; the predicate it shares
    with the batch is pinned by ``testing/integration/test_ingestion_repository.py``.
    """
    mocker.patch.object(repository, "count_pending", return_value=0)


def test_run_detail_scraping_job_success(mocker: MockerFixture, queue_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)

    # 1. Isolate the queue lookup to return only the mock
    mocker.patch.object(repository, "get_from_queue", return_value=[queue_mock])

    # 2. Create the Adapter mock respecting the Interface
    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.return_value = {"title": "Teste"}

    # 3. Isolate persistence
    mock_save = mocker.patch.object(repository, "save_raw_data")
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    # 4. Run the Worker injecting the dependencies
    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    # 5. Validate the orchestration
    mock_adapter.fetch_details.assert_called_once_with("doc-123")
    mock_save.assert_called_once_with(mock_db, "doc-123", {"title": "Teste"})
    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.DONE)
    # The raw payload and the queue status are committed atomically per item.
    mock_db.commit.assert_called_once()


def test_run_detail_scraping_job_rolls_back_when_save_fails(mocker: MockerFixture, queue_mock: ScrapingQueue) -> None:
    """If the raw payload cannot be saved, the item must roll back and not be marked DONE."""
    mock_db = mocker.Mock(spec=Session)

    mocker.patch.object(repository, "get_from_queue", return_value=[queue_mock])
    mocker.patch.object(repository, "save_raw_data", side_effect=Exception("deadlock"))
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.return_value = {"title": "Teste"}

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    mock_db.rollback.assert_called_once()
    mock_queue.assert_not_called()


def test_run_detail_scraping_job_not_found(mocker: MockerFixture, queue_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)

    mocker.patch.object(repository, "get_from_queue", return_value=[queue_mock])
    mock_save = mocker.patch.object(repository, "save_raw_data")
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.side_effect = AdapterNotFoundError("Não existe")

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    mock_save.assert_not_called()
    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.NOT_FOUND, error_msg="Não existe")


def test_run_detail_scraping_job_network_retry(mocker: MockerFixture, queue_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)
    queue_mock.retry_count = 1  # Still has retries left

    mocker.patch.object(repository, "get_from_queue", return_value=[queue_mock])
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.side_effect = AdapterNetworkError("Caiu a internet")

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    mock_queue.assert_called_once_with(
        mock_db, "doc-123", ScrapeStatus.NETWORK_ERROR, error_msg="Caiu a internet", increment_retry=True
    )


def test_run_detail_scraping_job_max_retries_exceeded(mocker: MockerFixture, queue_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)
    queue_mock.retry_count = 3  # Limit exceeded!

    mocker.patch.object(repository, "get_from_queue", return_value=[queue_mock])
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.side_effect = AdapterNetworkError("Caiu de novo")

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    # The Worker must detect that it went past 3 and raise it as FATAL
    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.FATAL_ERROR, error_msg="Caiu de novo")


def test_run_detail_scraping_job_direct_fatal_error(mocker: MockerFixture, queue_mock: ScrapingQueue) -> None:
    mock_db = mocker.Mock(spec=Session)
    # Even on the first attempt (retry=0), if it is a fatal error, it cannot try again
    queue_mock.retry_count = 0

    mocker.patch.object(repository, "get_from_queue", return_value=[queue_mock])
    mock_queue = mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    # Example: BeautifulSoup broke trying to read a nonexistent tag
    mock_adapter.fetch_details.side_effect = AdapterFatalError("HTML Malformado")

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter)

    mock_queue.assert_called_once_with(mock_db, "doc-123", ScrapeStatus.FATAL_ERROR, error_msg="HTML Malformado")


# ==========================================
# THE BATCH SIZE
# ==========================================


def test_run_detail_scraping_job_forwards_the_limit(mocker: MockerFixture, queue_mock: ScrapingQueue) -> None:
    """The bound is a decision of the caller; the worker must pass it on instead of widening it."""
    mock_db = mocker.Mock(spec=Session)
    get_from_queue = mocker.patch.object(repository, "get_from_queue", return_value=[queue_mock])
    mocker.patch.object(repository, "save_raw_data")
    mocker.patch.object(repository, "update_queue_status")

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.return_value = {"title": "Teste"}

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter, limit=7)

    assert get_from_queue.call_args.kwargs["limit"] == 7


def test_the_remaining_report_uses_the_policy_the_batch_used(mocker: MockerFixture, queue_mock: ScrapingQueue) -> None:
    """
    The count must read the very filters the batch read.

    A count that recomputed the windows would describe a slightly different queue every time, and
    "3 still pending" would stop meaning "the next run takes 3".
    """
    mock_db = mocker.Mock(spec=Session)
    get_from_queue = mocker.patch.object(repository, "get_from_queue", return_value=[queue_mock])
    mocker.patch.object(repository, "save_raw_data")
    mocker.patch.object(repository, "update_queue_status")
    count = mocker.patch.object(repository, "count_pending", return_value=42)

    mock_adapter = mocker.Mock(spec=IDetailAdapter)
    mock_adapter.fetch_details.return_value = {"title": "Teste"}

    worker.run_detail_scraping_job(mock_db, adapter=mock_adapter, limit=1)

    taken = get_from_queue.call_args.kwargs
    counted = count.call_args.kwargs
    assert counted["discovered_after"] == taken["discovered_after"]
    assert counted["scraped_before"] == taken["scraped_before"]
    assert counted["ignore_status"] == taken["ignore_status"]
