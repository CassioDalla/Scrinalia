from abc import ABC, abstractmethod
from collections.abc import Iterator


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
