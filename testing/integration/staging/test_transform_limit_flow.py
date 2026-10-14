"""
The transform bounded per run, through the use case rather than the query.

The repository test pins ``next_batch``; this one pins the *pipeline*: a 100-document scrape no longer
forces a full-collection transform, because a bounded run structures what it took and the next one
sees exactly the rest through the CDC.
"""

from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA
from scrinalia.domains.ingestion.models import RawData
from scrinalia.domains.staging.models import StagingDocument
from scrinalia.domains.staging.repository import SqlRawRecordSource
from scrinalia.domains.staging.worker import run_staging_pipeline


def _raw(index: int) -> RawData:
    return RawData(
        description_id=f"lote-{index}",
        payload={"title": f"Rua {index}", "Data de Produção": "Década de 1980"},
        content_hash=f"hash-lote-{index}",
        raw_title=f"Rua {index}",
    )


def test_a_limited_transform_leaves_the_rest_for_the_next_run(db_session) -> None:
    for index in range(3):
        db_session.add(_raw(index))
    db_session.flush()

    source = SqlRawRecordSource(db_session)

    run_staging_pipeline(db_session, PMC_SOURCE_SCHEMA, limit=2)

    assert db_session.query(StagingDocument).count() == 2
    assert source.count_pending() == 1

    run_staging_pipeline(db_session, PMC_SOURCE_SCHEMA, limit=2)

    assert db_session.query(StagingDocument).count() == 3
    assert source.count_pending() == 0


def test_a_forced_run_bounded_by_a_cursor_walks_the_whole_collection(db_session) -> None:
    """
    The parser-fix path, in batches: ``--force`` re-reads everything, and the cursor advances it.

    A forced run ignores the comparison, so it would structure the same page every time; this is
    the operation the limit exists for, and the cursor is what keeps it honest across runs.
    """
    for index in range(3):
        db_session.add(_raw(index))
    db_session.flush()

    run_staging_pipeline(db_session, PMC_SOURCE_SCHEMA, force=True, limit=2)

    assert db_session.query(StagingDocument).count() == 2

    run_staging_pipeline(db_session, PMC_SOURCE_SCHEMA, force=True, limit=2, after="lote-1")

    assert db_session.query(StagingDocument).count() == 3
    assert SqlRawRecordSource(db_session).count_pending(force=True, after="lote-2") == 0
