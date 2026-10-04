"""Integration tests of the date backfill path: force re-parse and parse-aware CDC."""

from datetime import date

from sqlalchemy import select

from memoria_curitibana.domains.archive.models import ArchiveDocument
from memoria_curitibana.domains.archive.workers.worker_archive_transfer import execute as run_transfer
from memoria_curitibana.domains.ingestion.models import RawData
from memoria_curitibana.domains.staging.models import StagingDocument
from memoria_curitibana.domains.staging.worker import run_staging_pipeline


def _raw(description_id: str = "date-1", raw_date: str = "Década de 1980", content_hash: str = "raw-hash-1") -> RawData:
    return RawData(
        description_id=description_id,
        payload={"Data de Produção": raw_date, "title": "Rua Izaac"},
        content_hash=content_hash,
        raw_title="Rua Izaac",
    )


# ==========================================
# STAGING: THE CDC CANNOT SEE A PARSER CHANGE
# ==========================================


def test_staging_parses_a_decade_into_a_date(db_session) -> None:
    db_session.add(_raw())
    db_session.flush()

    run_staging_pipeline(db_session)

    staging = db_session.get(StagingDocument, "date-1")
    assert staging.document_date == date(1980, 1, 1)


def test_the_cdc_skips_an_unchanged_payload_and_force_reparses_it(db_session) -> None:
    """Regression for the bug the fix exists for: a parser change never reached staging."""
    db_session.add(_raw())
    db_session.flush()
    run_staging_pipeline(db_session)

    staging = db_session.get(StagingDocument, "date-1")
    staging.document_date = None  # what the old parser produced
    db_session.flush()

    run_staging_pipeline(db_session)
    db_session.refresh(staging)
    assert staging.document_date is None  # the raw hash did not change, so it was skipped

    run_staging_pipeline(db_session, force=True)
    db_session.refresh(staging)
    assert staging.document_date == date(1980, 1, 1)


def test_force_reparses_every_record(db_session) -> None:
    for index in range(3):
        db_session.add(_raw(description_id=f"date-{index}", content_hash=f"raw-{index}"))
    db_session.flush()

    run_staging_pipeline(db_session, force=True)

    dates = db_session.scalars(select(StagingDocument.document_date)).all()
    assert dates == [date(1980, 1, 1)] * 3


# ==========================================================
# TRANSFER: THE ARCHIVE CDC KEYS ON THE PARSED RECORD
# ==========================================================


def test_a_parser_change_reaches_the_archive(db_session) -> None:
    db_session.add(_raw(description_id="date-9", raw_date="00/00/0000"))
    db_session.flush()
    run_staging_pipeline(db_session, force=True)
    run_transfer(db_session)

    archived = db_session.get(ArchiveDocument, "date-9")
    assert archived.document_date is None
    first_hash = archived.staging_content_hash

    # The parser learns a new expression: the raw payload is byte-identical.
    staging = db_session.get(StagingDocument, "date-9")
    staging.document_date = date(1996, 1, 1)
    db_session.flush()

    run_transfer(db_session)
    db_session.refresh(archived)

    assert archived.document_date == date(1996, 1, 1)
    assert archived.staging_content_hash != first_hash


def test_the_transfer_does_not_touch_a_human_approved_document(db_session) -> None:
    from memoria_curitibana.domains.archive.models import ArchiveReviewStatus

    db_session.add(_raw(description_id="date-10", raw_date="00/00/0000"))
    db_session.flush()
    run_staging_pipeline(db_session, force=True)
    run_transfer(db_session)

    archived = db_session.get(ArchiveDocument, "date-10")
    archived.review_status = ArchiveReviewStatus.HUMAN_APPROVED
    archived.document_date = date(1900, 1, 1)  # the archivist's decision
    db_session.flush()

    staging = db_session.get(StagingDocument, "date-10")
    staging.document_date = date(1996, 1, 1)
    db_session.flush()

    run_transfer(db_session)
    db_session.refresh(archived)

    assert archived.document_date == date(1900, 1, 1)
