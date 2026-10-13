"""
The scrape bounded per run.

The integration tests of the repository pin the query; this one pins the *run*: a batch takes what
the limit allows, writes it, and the next batch takes different rows — which is the whole point of
bounding the scrape, because without it a 100-document discovery always produced a full-queue scrape.

The adapter is a port double: the network is not the subject here, and a test that scraped the real
site would be a test of the site.
"""

from collections.abc import Sequence

from sqlalchemy import select

from scrinalia.core.runner_config import IngestionRunnerConfig
from scrinalia.domains.ingestion.models import RawData, ScrapeStatus, ScrapingQueue
from scrinalia.domains.ingestion.ports import IDetailAdapter, IDiscoveryAdapter
from scrinalia.domains.ingestion.repository import add_in_bulk, count_pending
from scrinalia.domains.ingestion.worker import run_detail_scraping_job, run_discovery_job


class RecordingDetailAdapter(IDetailAdapter):
    """A detail port that answers without a network and remembers which ids it was asked for."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def fetch_details(self, description_id: str) -> dict[str, str]:
        self.seen.append(description_id)
        return {"title": f"Documento {description_id}", "Data de Produção": "Década de 1920"}


class RecordingDiscoveryAdapter(IDiscoveryAdapter):
    """A discovery port that yields fixed pages, so the run's total can be asserted."""

    def __init__(self, pages: Sequence[Sequence[str]]) -> None:
        self.pages = list(pages)
        self.pages_walked = 0

    def fetch_new_ids(self, initial_page: int = 1, max_pages: int | None = None):
        for page in self.pages:
            if max_pages is not None and self.pages_walked >= max_pages:
                break
            self.pages_walked += 1
            yield list(page)


def _done(db_session) -> set[str]:
    return set(
        db_session.scalars(
            select(ScrapingQueue.description_id).where(ScrapingQueue.scrape_status == ScrapeStatus.DONE)
        ).all()
    )


def _pending(db_session) -> int:
    return count_pending(db_session, ignore_status=[ScrapeStatus.DONE])


def test_a_limited_scrape_leaves_the_rest_for_the_next_run(use_test_db, db_session) -> None:
    """2 + 2 + 1 over five discovered ids: every run takes different rows and the count drops."""
    ids = [f"limite_{index}" for index in range(5)]
    add_in_bulk(db_session, ids)
    db_session.commit()
    assert _pending(db_session) == 5

    first = RecordingDetailAdapter()
    run_detail_scraping_job(db_session, adapter=first, limit=2, config=IngestionRunnerConfig())

    assert len(first.seen) == 2
    assert _pending(db_session) == 3

    second = RecordingDetailAdapter()
    run_detail_scraping_job(db_session, adapter=second, limit=2, config=IngestionRunnerConfig())

    assert len(second.seen) == 2
    assert set(second.seen).isdisjoint(first.seen)
    assert _pending(db_session) == 1

    third = RecordingDetailAdapter()
    run_detail_scraping_job(db_session, adapter=third, limit=2, config=IngestionRunnerConfig())

    assert len(third.seen) == 1
    assert set(first.seen) | set(second.seen) | set(third.seen) == set(ids)
    assert _pending(db_session) == 0

    # The bound is on the queue, not on what got written.
    assert set(db_session.scalars(select(RawData.description_id)).all()) == set(ids)
    assert _done(db_session) == set(ids)


def test_the_discovery_phase_reports_what_it_enqueued(use_test_db, db_session) -> None:
    """``run`` chains the two phases, so discovery answers with a total instead of only logging it."""
    adapter = RecordingDiscoveryAdapter([["novo_1", "novo_2"], ["novo_2", "novo_3"]])

    inserted = run_discovery_job(db_session, adapter=adapter, max_pages=1)

    assert inserted == 2
    assert adapter.pages_walked == 1
    assert set(db_session.scalars(select(ScrapingQueue.description_id)).all()) == {"novo_1", "novo_2"}

    # The second page brings one genuinely new id; the repeat is ignored by the unique key.
    assert run_discovery_job(db_session, adapter=adapter) == 1
