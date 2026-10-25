"""The origin as an object: its queue isolation, its manual path and its scheduled slot.

These are database tests because the three claims are about what the database holds: the queue
filters by origin, the manual entry writes raw + staging with the origin and reaches `PENDING_AI`
through the same transfer, and the scheduler enqueues one `ingestion` run per origin while the
partial unique index keeps one slot per origin.
"""

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import WorkerRunAlreadyActiveError
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.archive.models.operations import WorkerRun
from scrinalia.domains.archive.workers import worker_archive_transfer, worker_ner
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger
from scrinalia.domains.archive.workers.scheduler import SchedulerConfig, SchedulerService
from scrinalia.domains.ingestion import repository
from scrinalia.domains.ingestion.exceptions import DuplicateManualRecordError, OriginDisabledError
from scrinalia.domains.ingestion.models import IngestionOrigin, RawData, ScrapeStatus, ScrapingQueue
from scrinalia.domains.ingestion.schemas import IngestionRunRequest, ManualIngestionRequest
from scrinalia.domains.ingestion.service import IngestionOriginService
from scrinalia.domains.staging.models import StagingDocument
from scrinalia.domains.staging.worker import run_staging_pipeline

AUTHOR = Author(name="curador")


@contextmanager
def _shared_session(db):
    """Hands the test's session to the ledger and the scheduler without closing it on the way out."""
    yield db


@pytest.fixture
def origins(db_session):
    db_session.add(IngestionOrigin(code="pmc", enabled=True, config={}, options={}))
    db_session.add(IngestionOrigin(code="manual", enabled=True, config={}, options={}))
    db_session.flush()


def test_the_queue_is_read_one_origin_at_a_time(db_session, origins) -> None:
    repository.add_in_bulk(db_session, ["pmc-1", "pmc-2"], origin_code="pmc")
    repository.add_in_bulk(db_session, ["manual-1"], origin_code="manual")
    db_session.flush()

    pmc_rows = repository.get_from_queue(db_session, origin_code="pmc")
    manual_rows = repository.get_from_queue(db_session, origin_code="manual")

    assert {row.description_id for row in pmc_rows} == {"pmc-1", "pmc-2"}
    assert {row.description_id for row in manual_rows} == {"manual-1"}
    assert repository.count_pending(db_session, origin_code="pmc") == 2
    assert repository.count_pending(db_session, origin_code="manual") == 1


def test_the_transform_resolves_the_schema_of_each_record(db_session, origins) -> None:
    """
    The same run reads the reference site's labels and the manual form's keys.

    This is the boundary #44 draws: the transform is source-agnostic, and the origin of *the record*
    selects its vocabulary. A run that applied one schema to both would empty the other's columns.
    """
    repository.save_raw_data(
        db_session,
        "pmc-1",
        {"title": "Planta", "Código de Referência": "BR PR PMC 001"},
        origin_code="pmc",
    )
    repository.save_raw_data(
        db_session,
        "manual-1",
        {"title": "Ofício digitado", "reference_code": "BR PR MAN 001"},
        origin_code="manual",
    )
    db_session.flush()

    run_staging_pipeline(db_session)

    pmc = db_session.get(StagingDocument, "pmc-1")
    manual = db_session.get(StagingDocument, "manual-1")
    assert pmc is not None and pmc.reference_code == "BR PR PMC 001"
    assert manual is not None and manual.reference_code == "BR PR MAN 001"
    assert pmc.origin_code == "pmc"
    assert manual.origin_code == "manual"


def test_manual_ingestion_stages_the_record_and_queues_the_transfer(db_session, origins) -> None:
    service = IngestionOriginService(
        db_session, ledger=WorkerRunLedger(session_factory=lambda: _shared_session(db_session))
    )

    response = service.create_manual(
        ManualIngestionRequest(
            description_id="manual-test-1",
            title="Ofício do Prefeito",
            reference_code="BR PR MAN 001",
            document_date=date(1929, 7, 5),
            scope_content="Um ofício sobre a cidade.",
            indexing_points="ofício, prefeitura",
        ),
        author=AUTHOR,
    )

    assert response.data.description_id == "manual-test-1"
    assert response.data.transfer_queued is True
    assert response.data.review_status == "PENDING_AI"
    assert response.data.transfer_run_id is not None

    raw = db_session.scalar(select(RawData).where(RawData.description_id == "manual-test-1"))
    assert raw is not None
    assert raw.origin_code == "manual"
    assert raw.created_by == "curador"
    assert raw.payload["scope_content"] == "Um ofício sobre a cidade."

    staged = db_session.get(StagingDocument, "manual-test-1")
    assert staged is not None
    assert staged.origin_code == "manual"
    assert staged.title == "Ofício do Prefeito"
    assert staged.reference_code == "BR PR MAN 001"
    assert str(staged.document_date) == "1929-07-05"

    queue = db_session.scalar(select(ScrapingQueue).where(ScrapingQueue.description_id == "manual-test-1"))
    assert queue is not None and queue.scrape_status is ScrapeStatus.DONE

    transfer = db_session.get(WorkerRun, response.data.transfer_run_id)
    assert transfer is not None
    assert transfer.worker_name == "transfer"
    assert transfer.origin_code is None

    # The manual record is not an approval: the same transfer creates the archive description as
    # PENDING_AI, and the NER queue already sees it. This is the guarantee the form promises.
    worker_archive_transfer.execute(db_session)
    archived = db_session.get(ArchiveDocument, "manual-test-1")
    assert archived is not None
    assert archived.review_status is ArchiveReviewStatus.PENDING_AI
    assert archived.origin_code == "manual"
    assert worker_ner.count_pending(db_session) >= 1


def test_a_duplicate_manual_id_is_refused_before_the_write(db_session, origins) -> None:
    service = IngestionOriginService(
        db_session, ledger=WorkerRunLedger(session_factory=lambda: _shared_session(db_session))
    )
    request = ManualIngestionRequest(description_id="manual-dup", title="Primeiro")
    service.create_manual(request, author=AUTHOR)

    with pytest.raises(DuplicateManualRecordError):
        service.create_manual(request, author=AUTHOR)


def test_a_paused_manual_origin_refuses_the_form(db_session, origins) -> None:
    origin = db_session.scalar(select(IngestionOrigin).where(IngestionOrigin.code == "manual"))
    assert origin is not None
    origin.enabled = False
    db_session.flush()

    service = IngestionOriginService(
        db_session, ledger=WorkerRunLedger(session_factory=lambda: _shared_session(db_session))
    )
    with pytest.raises(OriginDisabledError):
        service.create_manual(ManualIngestionRequest(title="Pausado"), author=AUTHOR)


def test_one_ingestion_slot_per_origin(db_session, origins) -> None:
    service = IngestionOriginService(
        db_session, ledger=WorkerRunLedger(session_factory=lambda: _shared_session(db_session))
    )

    first = service.trigger("pmc", IngestionRunRequest(pages=1), requested_by=AUTHOR)
    second = service.trigger("manual", IngestionRunRequest(pages=0), requested_by=AUTHOR)

    assert first.worker_name == "ingestion" and first.origin_code == "pmc"
    assert second.worker_name == "ingestion" and second.origin_code == "manual"
    with pytest.raises(WorkerRunAlreadyActiveError):
        service.trigger("pmc", IngestionRunRequest(pages=1), requested_by=AUTHOR)


def test_the_scheduler_enqueues_one_ingestion_run_per_due_origin(db_session, origins) -> None:
    origin = db_session.scalar(select(IngestionOrigin).where(IngestionOrigin.code == "pmc"))
    assert origin is not None
    origin.cron = "*/5 * * * *"
    origin.timezone = "UTC"
    origin.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()

    scheduler = SchedulerService(SchedulerConfig(once=True), session_factory=lambda: _shared_session(db_session))
    assert scheduler.tick() == 1

    run = db_session.scalar(select(WorkerRun).where(WorkerRun.worker_name == "ingestion"))
    assert run is not None
    assert run.origin_code == "pmc"
    assert run.status.value == "QUEUED"
    assert origin.last_enqueued_at is not None
    assert origin.next_run_at is not None and origin.next_run_at > datetime.now(UTC)


def test_a_due_origin_is_skipped_while_its_run_is_active(db_session, origins) -> None:
    origin = db_session.scalar(select(IngestionOrigin).where(IngestionOrigin.code == "pmc"))
    assert origin is not None
    origin.cron = "*/5 * * * *"
    origin.timezone = "UTC"
    origin.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()

    ledger = WorkerRunLedger(session_factory=lambda: _shared_session(db_session))
    ledger.enqueue(
        "ingestion",
        requested_by=AUTHOR,
        engine_name=None,
        preset=None,
        config={},
        origin_code="pmc",
    )

    scheduler = SchedulerService(SchedulerConfig(once=True), session_factory=lambda: _shared_session(db_session))
    assert scheduler.tick() == 1

    runs = db_session.scalars(select(WorkerRun).where(WorkerRun.worker_name == "ingestion")).all()
    assert len(runs) == 1
    assert origin.last_skipped_at is not None
