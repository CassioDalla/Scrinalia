"""
The ingestion host CLI.

Two things are pinned here and nowhere else: that the run policy follows the flags that were given
*wrapped around* the dataclass defaults instead of a second copy of the numbers, and that ``run``
really chains the two phases — the difference between the CLI being a real entry point and a
collection of flags that happen to parse.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from scrinalia.core.runner_config import IngestionRunnerConfig
from scrinalia.domains.ingestion import sources, worker
from scrinalia.domains.ingestion.exceptions import OriginNotFoundError
from scrinalia.domains.ingestion.ports import IDetailAdapter, IDiscoveryAdapter


def test_the_config_follows_the_flags_and_keeps_the_code_defaults() -> None:
    parser = worker._build_parser()

    untouched = parser.parse_args(["scrape", "--origin", "pmc", "--limit", "100"])
    assert worker.config_from_args(untouched) == IngestionRunnerConfig()

    overridden = parser.parse_args(
        [
            "scrape",
            "--origin",
            "pmc",
            "--max-retries",
            "0",
            "--discovery-window-days",
            "7",
            "--scraped-ttl-days",
            "2",
        ]
    )
    assert worker.config_from_args(overridden) == IngestionRunnerConfig(
        max_retries=0, discovery_window_days=7, scraped_ttl_days=2
    )


def test_a_zero_limit_is_a_usage_error() -> None:
    """``LIMIT 0`` would read nothing and exit successfully, which an operator cannot tell from empty."""
    with pytest.raises(SystemExit):
        worker._build_parser().parse_args(["scrape", "--origin", "pmc", "--limit", "0"])


def test_run_chains_the_two_phases(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    class _Port(IDiscoveryAdapter, IDetailAdapter):
        """Stands in for an adapter: the CLI must not care which phase object it receives."""

        def fetch_new_ids(self, initial_page: int = 1, max_pages: int | None = None) -> Iterator[list[str]]:
            return iter(())

        def fetch_details(self, description_id: str) -> dict[str, str]:
            return {}

    adapters = sources.OriginAdapters(code="pmc", discovery=_Port(), detail=_Port())
    monkeypatch.setattr(sources, "get_adapters", lambda code=None, db=None: adapters)

    @contextmanager
    def _db():
        yield object()

    monkeypatch.setattr(worker, "get_db", _db)
    monkeypatch.setattr(
        worker,
        "run_discovery_job",
        lambda db, adapter, max_pages=None, origin_code=None: calls.append(("discover", max_pages)),
    )
    monkeypatch.setattr(
        worker, "run_detail_scraping_job", lambda db, **kwargs: calls.append(("scrape", kwargs["limit"]))
    )

    assert worker.main(["run", "--origin", "pmc", "--pages", "2", "--limit", "5"]) == 0
    assert calls == [("discover", 2), ("scrape", 5)]


def test_an_unknown_origin_fails_as_a_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrong origin is a sentence and an exit code, not a scrape that starts and then dies."""

    @contextmanager
    def _db():
        yield object()

    def _unknown(code=None, db=None):
        raise OriginNotFoundError("Origem 'inexistente' não existe.")

    monkeypatch.setattr(worker, "get_db", _db)
    monkeypatch.setattr(sources, "get_adapters", _unknown)

    assert worker.main(["scrape", "--origin", "inexistente"]) == 1
