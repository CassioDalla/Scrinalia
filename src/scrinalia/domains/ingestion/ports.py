from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceConfig:
    """
    What a scraping adapter needs to reach its origin, declared by the caller.

    Deliberately a parameter and not a global read. The adapter is the *institution-specific* piece
    of the ingestion: it knows one site's URLs and its HTML. Making it read ``settings`` tied it to
    one deployment and made a second origin impossible — the plural-ingestion work needs an
    arbitrary number of them, each with its own configuration.

    What is **not** here is as deliberate as what is: the selectors, the field names scraped from
    the page and the pagination markup stay inside the adapter, because they are the contract with
    *that* site and no configuration value can abstract an HTML layout. This object carries only
    what an operator can meaningfully change without editing the adapter.
    """

    base_url: str
    detail_url: str
    #: Politeness delay between requests, in seconds.
    delay_requests: float = 0.5


class AdapterNotFoundError(Exception):
    """Thrown when the document does not exist in the external source (e.g., 404)."""

    ...


class AdapterNetworkError(Exception):
    """Thrown when connection instability occurs (e.g., timeout)."""

    ...


class AdapterFatalError(Exception):
    """Thrown when data is corrupted or the layout is broken."""

    ...


class IDiscoveryAdapter(ABC):
    """Contract for adapters seeking NEW IDs in the legacy system."""

    @abstractmethod
    def fetch_new_ids(self, initial_page: int = 1, max_pages: int | None = None) -> Iterator[list[str]]:
        """It should yield lists of IDs found per page/batch."""
        ...


class IDetailAdapter(ABC):
    """Contract for adapters that extract metadata from a specific ID."""

    @abstractmethod
    def fetch_details(self, description_id: str) -> dict[str, str]:
        """It must return a dictionary containing the raw data ready for Staging."""
        ...
