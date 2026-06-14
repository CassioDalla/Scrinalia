from abc import ABC, abstractmethod
from collections.abc import Iterator


class AdapterNotFoundError(Exception):
    """Lançado quando o documento não existe na fonte externa (ex: 404)."""

    pass


class AdapterNetworkError(Exception):
    """Lançado quando ocorre instabilidade de conexão (ex: Timeout)."""

    pass


class AdapterFatalError(Exception):
    """Lançado quando os dados estão corrompidos ou o layout quebrou."""

    pass


class IDiscoveryAdapter(ABC):
    """Contrato para adaptadores que buscam NOVOS IDs no sistema legado."""

    @abstractmethod
    def fetch_new_ids(self, initial_page: int = 1, max_pages: int | None = None) -> Iterator[list[str]]:
        """Deve yieldar listas de IDs encontrados por página/lote."""
        pass


class IDetailAdapter(ABC):
    """Contrato para adaptadores que extraem os metadados de um ID específico."""

    @abstractmethod
    def fetch_details(self, description_id: str) -> dict[str, str]:
        """Deve retornar um dicionário com os dados brutos prontos para a Staging."""
        pass
