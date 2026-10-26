"""The origin as an object: its queue isolation, its manual path and its scheduled slot.

These are database tests because the three claims are about what the database holds: the queue
filters by origin, the manual entry writes raw + staging with the origin and reaches `PENDING_AI`
through the same transfer, and the scheduler enqueues one `ingestion` run per origin while the
partial unique index keeps one slot per origin.
"""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import WorkerRunAlreadyActiveError
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveReviewStatus
from scrinalia.domains.archive.models.operations import WorkerRun
from scrinalia.domains.archive.schemas.responses import RouteMessageCode
from scrinalia.domains.archive.workers import worker_archive_transfer, worker_ner
from scrinalia.domains.archive.workers.ledger import WorkerRunLedger
from scrinalia.domains.archive.workers.scheduler import SchedulerConfig, SchedulerService
from scrinalia.domains.ingestion import repository, worker
from scrinalia.domains.ingestion.adapters.csv import CSV_SOURCE_SCHEMA
from scrinalia.domains.ingestion.csv_import import CsvRowStatus
from scrinalia.domains.ingestion.exceptions import (
    CsvImportLimitError,
    DuplicateManualRecordError,
    OriginDisabledError,
)
from scrinalia.domains.ingestion.models import IngestionOrigin, RawData, ScrapeStatus, ScrapingQueue
from scrinalia.domains.ingestion.schemas import (
    CsvImportRequest,
    CsvImportRow,
    IngestionOriginUpdateRequest,
    IngestionRunRequest,
    ManualIngestionRequest,
)
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
    db_session.add(IngestionOrigin(code="csv", enabled=True, config={}, options={}))
    db_session.flush()


# ==========================================
# THE PAGE'S READ: SOURCES AND ENTRIES (#206)
# ==========================================


def test_the_read_separates_the_sources_from_the_entry_paths(db_session, origins) -> None:
    """A row makes an origin configured; the definition says whether it is a source or an entry."""
    page = IngestionOriginService(db_session).list_origins()

    assert [origin.code for origin in page.origins] == ["pmc", "manual", "csv"]
    assert {origin.code: origin.configurable for origin in page.origins} == {
        "pmc": True,
        "manual": False,
        "csv": False,
    }
    assert page.available == []


def test_a_fresh_install_offers_the_source_and_keeps_the_entries_readable(db_session) -> None:
    """The seeded entries are not sources: the page is empty and the picker offers the source."""
    db_session.add(IngestionOrigin(code="manual", enabled=True, config={}, options={}))
    db_session.add(IngestionOrigin(code="csv", enabled=True, config={}, options={}))
    db_session.flush()

    page = IngestionOriginService(db_session).list_origins()

    assert [origin.code for origin in page.origins] == ["manual", "csv"]
    assert all(origin.configurable is False for origin in page.origins)
    assert [origin.code for origin in page.available] == ["pmc"]
    assert page.available[0].label == "Acervo de referência (PMC)"


def test_adding_the_available_source_activates_it(db_session) -> None:
    """The picker's write is the existing upsert: it creates the row enabled and records the author."""
    service = IngestionOriginService(db_session)
    assert [origin.code for origin in service.list_origins().available] == ["pmc"]

    added = service.update_origin(
        "pmc",
        IngestionOriginUpdateRequest(enabled=True, config={}, options={}),
        author=AUTHOR,
    )

    assert added.code == "pmc"
    assert added.enabled is True
    assert added.configurable is True
    page = service.list_origins()
    assert [origin.code for origin in page.origins] == ["pmc"]
    assert page.available == []
    row = db_session.get(IngestionOrigin, "pmc")
    assert row is not None and row.enabled is True and row.updated_by == AUTHOR.name


def test_a_paused_source_keeps_its_card(db_session, origins) -> None:
    """Pausing is the lifecycle, not a deletion: the row stays and the page still lists it."""
    pmc = db_session.get(IngestionOrigin, "pmc")
    assert pmc is not None
    pmc.enabled = False
    db_session.flush()

    page = IngestionOriginService(db_session).list_origins()
    by_code = {origin.code: origin for origin in page.origins}

    assert by_code["pmc"].enabled is False
    assert by_code["pmc"].configurable is True


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
            # What the archivist types: the language profile reads it, and the spelling is kept.
            document_date="05/07/1929",
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
    assert staged.date_expression == "05/07/1929"
    assert str(response.data.document_date) == "1929-07-05"
    assert response.data.date_expression == "05/07/1929"

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


# ==========================================
# THE CSV IMPORT (#191)
# ==========================================


def _csv_service(db_session) -> IngestionOriginService:
    return IngestionOriginService(
        db_session, ledger=WorkerRunLedger(session_factory=lambda: _shared_session(db_session))
    )


def _row(identifier: str, line: int, title: str, **fields: str) -> CsvImportRow:
    return CsvImportRow(line=line, description_id=identifier, fields={"Título": title, **fields})


def test_the_csv_import_stages_the_accepted_rows_and_queues_one_transfer(db_session, origins) -> None:
    service = _csv_service(db_session)

    response = service.import_csv(
        CsvImportRequest(
            rows=[
                _row("csv-1", 2, "Ofício A", **{"Código de referência": "BR A"}),
                _row("csv-2", 3, "Ofício B", **{"Data de produção": "05/07/1929"}),
                _row("csv-2", 4, "Repetido no arquivo"),
                _row("csv-3", 5, "   "),
            ]
        ),
        author=AUTHOR,
    )

    data = response.data
    assert response.code is RouteMessageCode.CSV_IMPORT_QUEUED
    assert (data.received, data.accepted, data.duplicated, data.invalid) == (4, 2, 1, 1)
    assert data.transfer_queued is True and data.transfer_run_id is not None
    assert data.review_status == "PENDING_AI"
    assert [(row.line, row.status) for row in data.rows] == [
        (2, CsvRowStatus.ACCEPTED),
        (3, CsvRowStatus.ACCEPTED),
        (4, CsvRowStatus.DUPLICATED),
        (5, CsvRowStatus.INVALID),
    ]

    raws = {raw.description_id: raw for raw in db_session.scalars(select(RawData).where(RawData.origin_code == "csv"))}
    assert set(raws) == {"csv-1", "csv-2"}
    assert raws["csv-1"].created_by == "curador"
    assert raws["csv-1"].payload["Título"] == "Ofício A"
    assert raws["csv-1"].raw_title == "Ofício A"

    queues = {
        queue.description_id: queue
        for queue in db_session.scalars(select(ScrapingQueue).where(ScrapingQueue.origin_code == "csv"))
    }
    assert set(queues) == {"csv-1", "csv-2"}
    assert all(queue.scrape_status is ScrapeStatus.DONE for queue in queues.values())

    staged = db_session.get(StagingDocument, "csv-1")
    assert staged is not None and staged.origin_code == "csv"
    assert staged.title == "Ofício A" and staged.reference_code == "BR A"
    staged_two = db_session.get(StagingDocument, "csv-2")
    assert staged_two is not None and staged_two.document_date is not None
    assert staged_two.document_date.isoformat() == "1929-07-05"

    # Not an approval: the transfer creates the archive description as PENDING_AI and the AI queues
    # see it, exactly like the manual form.
    worker_archive_transfer.execute(db_session)
    archived = db_session.get(ArchiveDocument, "csv-1")
    assert archived is not None
    assert archived.review_status is ArchiveReviewStatus.PENDING_AI
    assert archived.origin_code == "csv"
    assert worker_ner.count_pending(db_session) >= 1


def test_an_id_the_collection_already_has_is_reported_duplicated(db_session, origins) -> None:
    repository.save_raw_data(db_session, "csv-1", {"Título": "O original"}, origin_code="csv")
    db_session.flush()

    response = _csv_service(db_session).import_csv(
        CsvImportRequest(rows=[_row("csv-1", 2, "A tentativa nova")]),
        author=AUTHOR,
    )

    assert response.code is RouteMessageCode.CSV_IMPORT_REFUSED
    assert (response.data.accepted, response.data.duplicated) == (0, 1)
    assert response.data.rows[0].status is CsvRowStatus.DUPLICATED
    assert response.data.rows[0].issues[0].code.value == "ALREADY_EXISTS"

    raw = db_session.scalar(select(RawData).where(RawData.description_id == "csv-1"))
    assert raw is not None and raw.payload == {"Título": "O original"}


def test_the_csv_import_refuses_more_rows_than_the_limit(db_session, origins, monkeypatch) -> None:
    monkeypatch.setattr("scrinalia.domains.ingestion.service.MAX_CSV_ROWS", 1)

    with pytest.raises(CsvImportLimitError, match="no máximo 1 linhas"):
        _csv_service(db_session).import_csv(
            CsvImportRequest(rows=[_row("csv-1", 2, "A"), _row("csv-2", 3, "B")]),
            author=AUTHOR,
        )


def test_a_paused_csv_origin_refuses_the_import(db_session, origins) -> None:
    origin = db_session.scalar(select(IngestionOrigin).where(IngestionOrigin.code == "csv"))
    assert origin is not None
    origin.enabled = False
    db_session.flush()

    with pytest.raises(OriginDisabledError):
        _csv_service(db_session).import_csv(CsvImportRequest(rows=[_row("csv-1", 2, "A")]), author=AUTHOR)


def test_the_csv_origin_counts_like_the_manual_one(db_session, origins) -> None:
    _csv_service(db_session).import_csv(
        CsvImportRequest(rows=[_row("csv-1", 2, "A"), _row("csv-2", 3, "B")]),
        author=AUTHOR,
    )

    assert worker.count_processed(db_session, "csv") == 2
    assert worker.count_pending(db_session, "csv") == 0
    assert worker.count_failed(db_session, "csv") == 0


def test_the_staging_window_stages_only_the_named_ids(db_session, origins) -> None:
    repository.save_raw_data(db_session, "csv-1", {"Título": "Um"}, origin_code="csv")
    repository.save_raw_data(db_session, "csv-2", {"Título": "Dois"}, origin_code="csv")
    db_session.flush()

    run_staging_pipeline(db_session, source_schema=CSV_SOURCE_SCHEMA, origin_code="csv", description_ids=["csv-1"])

    assert db_session.get(StagingDocument, "csv-1") is not None
    assert db_session.get(StagingDocument, "csv-2") is None


def test_a_transfer_already_in_flight_says_the_rows_enter_the_next_one(db_session, origins, mocker) -> None:
    """
    The second promise: the rows are staged and the response says they enter the next transfer.

    The active run is simulated at the ledger's boundary instead of by a real unique-index violation,
    because the suite hands the ledger the test's own session: an ``IntegrityError`` there poisons the
    session the assertions below need. The unique-index behaviour itself is pinned by
    ``test_one_ingestion_slot_per_origin`` and the ledger's own tests.
    """
    service = _csv_service(db_session)
    mocker.patch.object(service.ledger, "enqueue", side_effect=WorkerRunAlreadyActiveError("já existe"))

    response = service.import_csv(CsvImportRequest(rows=[_row("csv-1", 2, "A")]), author=AUTHOR)

    assert response.code is RouteMessageCode.CSV_IMPORT_STAGED
    assert response.data.transfer_queued is False
    assert response.data.accepted == 1
    assert db_session.get(StagingDocument, "csv-1") is not None


def test_a_manual_record_carries_every_isad_field_into_staging(db_session, origins) -> None:
    """
    The form's whole vocabulary reaches staging, one column per field (#192).

    The service iterates ``MANUAL_FIELDS``, and the pin in ``test_sources.py`` keeps that tuple equal
    to the request model; what this test adds is the other half: every field the model accepts is a
    column the staging transform fills, so the archive can receive it on the transfer.
    """
    values = {
        "reference_code": "BR PRPMC 001",
        "level": "Dossiê",
        "parent_reference_code": "BR PRPMC",
        "dimension_support": "2 folhas",
        "producers": "Prefeitura Municipal",
        "admin_bio_history": "Criada em 1912.",
        "admin_archival_history": "Transferida ao arquivo em 1998.",
        "provenance": "Doação da família",
        "scope_content": "Nomeação de servidor.",
        "appraisal_destruction": "Guarda permanente.",
        "accruals": "Sem incorporações previstas.",
        "arrangement": "Ordenado por data.",
        "access_conditions": "Aberto à consulta.",
        "reproduction_conditions": "Reprodução permitida com citação.",
        "language_name": "Português",
        "physical_characteristics": "Papel; tinta ferrogálica.",
        "finding_aids": "Índice onomástico da série.",
        "originals_location": "Arquivo Central, caixa 12.",
        "copies_location": "Microfilme 3.",
        "related_units": "BR PRPMC 002",
        "publication_notes": "Diário Oficial de 1929.",
        "conservation_notes": "Bordas rasgadas.",
        "general_notes": "Ver o processo irmão.",
        "archivist_notes": "Descrição revisada em 2026.",
        "rules_conventions": "ISAD(G) e NOBRADE.",
        "indexing_points": "urbanismo, obras",
        "original_url": "https://arquivo.example/registro/42",
        "thumb_down_link": "https://arquivo.example/42.jpg",
    }
    request = ManualIngestionRequest.model_validate(
        {
            "description_id": "manual-full",
            "title": "Ofício completo",
            "document_date": "1951-1953",
            **values,
        }
    )

    service = IngestionOriginService(
        db_session, ledger=WorkerRunLedger(session_factory=lambda: _shared_session(db_session))
    )
    service.create_manual(request, author=AUTHOR)

    staged = db_session.get(StagingDocument, "manual-full")
    assert staged is not None
    assert staged.title == "Ofício completo"
    # The interval became a real date at the precision the source has, and the spelling stayed.
    assert str(staged.document_date) == "1951-01-01"
    assert staged.date_expression == "1951-1953"

    for name, value in values.items():
        assert getattr(staged, name) == value, f"{name} não chegou ao staging"


def test_the_manual_payload_carries_the_date_as_it_was_typed(db_session, origins) -> None:
    """
    The date is stored as text and parsed once, by the staging transform.

    Converting it to ISO in the service would parse the same value twice and throw the spelling
    away — and the spelling is what the archive shows for an approximate date.
    """
    service = IngestionOriginService(
        db_session, ledger=WorkerRunLedger(session_factory=lambda: _shared_session(db_session))
    )
    service.create_manual(
        ManualIngestionRequest(description_id="manual-date", title="Foto", document_date="Década de 1980"),
        author=AUTHOR,
    )

    raw = db_session.scalar(select(RawData).where(RawData.description_id == "manual-date"))
    assert raw is not None
    assert raw.payload["document_date"] == "Década de 1980"

    staged = db_session.get(StagingDocument, "manual-date")
    assert staged is not None
    assert str(staged.document_date) == "1980-01-01"
    assert staged.date_expression == "Década de 1980"
