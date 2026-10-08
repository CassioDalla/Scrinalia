from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class SourceSchema:
    """
    The vocabulary of one origin: which of its fields becomes which staging attribute.

    Declared next to :class:`SourceConfig` because both are the origin's contract — one says *where*
    it is, the other says *what its fields are called*. The labels on the left are the site's own
    (they are scraped from the page), so they are **never translated**: translating one would make it
    stop matching the payload. What changed is where they live — out of the staging transform, which
    is domain logic, and into the origin's declaration, which is deployment data.

    ``title_key``/``url_key``/``attachment_key`` are the keys the **adapter** writes, not the site's
    labels. They belong to the same contract: an adapter that emits different names declares them
    here instead of forcing the transform to know about one site. ``field_map`` maps a source key to
    the staging attribute it fills, so an adapter whose thumbnail key is ``thumb_url`` still lands on
    the ``thumb_down_link`` column by declaring it.

    The mapping is read-only by convention: the dataclass is frozen, and nothing may rewrite the
    dictionary after construction.
    """

    code: str
    #: Source label -> staging attribute. Two labels for the same attribute collapse into one value.
    field_map: Mapping[str, str]
    #: The key the adapter writes the title under.
    title_key: str = "title"
    #: The key the adapter writes the page URL under.
    url_key: str = "_url_origem"
    #: The key the adapter writes the attachment link under.
    attachment_key: str = "attch_down_link"
    #: Source fields that may carry the date, most specific first.
    date_keys: tuple[str, ...] = field(default_factory=tuple)
    #: How two values of the same attribute collapse into one (``a | b``). Some origins name the
    #: same thing twice (four spellings of the superior unit), and losing one would lose evidence.
    join_separator: str = " | "


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
