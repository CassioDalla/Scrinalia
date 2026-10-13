"""
Which origin a deployment reads, and where each origin's vocabulary is declared.

The registry exists for the same reason ``core/language`` does: an origin is selected by name and
resolved once, so a second one is an entry plus a module instead of a branch inside the transform.
``ACERVO_SOURCE`` names it, and the resolution **fails fast** when it is unset — a staging run with
no field map would file every column as unknown, and an empty staging row is worse than an error.

The concrete schemas live next to the adapters that read those sites: an origin's vocabulary is only
meaningful together with the code that extracts it.

The origin's **ports** are registered here too, for the same reason: an adapter built by naming a
concrete site inside the job cannot be pointed at another one. And an origin is not necessarily a
paginated site — a CSV ingestion lists rows and has no detail page, an origin fed identifiers from
elsewhere has the opposite shape — so each entry declares which of the two phases it implements, and
asking for one it does not have is a sentence instead of an ``AttributeError``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from scrinalia.core.config import settings
from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA, PMCScraperAdapter
from scrinalia.domains.ingestion.ports import IDetailAdapter, IDiscoveryAdapter, SourceConfig, SourceSchema

#: Every origin the package ships. Adding one is adding an entry here and a schema next to its
#: adapter — and, when plural ingestion arrives, a row naming the origin on each raw record.
SOURCES: dict[str, SourceSchema] = {PMC_SOURCE_SCHEMA.code: PMC_SOURCE_SCHEMA}


@dataclass(frozen=True)
class OriginAdapters:
    """
    The ports one origin implements, resolved as a pair.

    Both fields are optional on purpose. The ingestion job has two ports and an origin may implement
    only one of them: a manual CSV ingestion lists rows and has no detail page to fetch, and an
    origin that receives its identifiers from elsewhere fetches details it was told about. Declaring
    the phase instead of failing deep inside the job is what keeps "another origin" a registry entry.
    """

    code: str
    discovery: IDiscoveryAdapter | None = None
    detail: IDetailAdapter | None = None

    def require_discovery(self) -> IDiscoveryAdapter:
        """The discovery port, or a sentence naming the phase this origin does not have."""
        if self.discovery is None:
            raise ValueError(f"Origin {self.code!r} declares no discovery phase.")
        return self.discovery

    def require_detail(self) -> IDetailAdapter:
        """The detail port, or a sentence naming the phase this origin does not have."""
        if self.detail is None:
            raise ValueError(f"Origin {self.code!r} declares no detail phase.")
        return self.detail


def _build_pmc_adapters() -> OriginAdapters:
    """
    The reference origin: one adapter object, because this site implements both ports.

    The fail-fast on the missing URLs is deliberate: the adapter used to build ``str(None)`` into the
    URL and the scrape broke much later with a confusing network error.
    """
    if not settings.PUBLIC_SCRAPE_URL or not settings.PUBLIC_SCRAPE_DETAIL_URL:
        raise ValueError("PUBLIC_SCRAPE_URL and PUBLIC_SCRAPE_DETAIL_URL must be set to scrape the source site.")

    adapter = PMCScraperAdapter(
        SourceConfig(base_url=settings.PUBLIC_SCRAPE_URL, detail_url=settings.PUBLIC_SCRAPE_DETAIL_URL)
    )
    return OriginAdapters(code=PMC_SOURCE_SCHEMA.code, discovery=adapter, detail=adapter)


#: Every origin the package can read, by code. Same shape as ``SOURCES``, and the same selector
#: resolves both: naming an origin names its field vocabulary *and* its ports.
ADAPTERS: dict[str, Callable[[], OriginAdapters]] = {PMC_SOURCE_SCHEMA.code: _build_pmc_adapters}


@lru_cache
def get_source_schema(code: str | None = None) -> SourceSchema:
    """
    The active origin's vocabulary: the explicit code wins, then ``ACERVO_SOURCE``.

    There is **no default**. A fallback would make an installation that never declared its origin
    read the reference site's labels, which is the "the default is the reference collection" defect ADR 0008 removed
    from the collection vocabulary — the same mistake in a different place.
    """
    resolved = code or settings.ACERVO_SOURCE
    if not resolved:
        raise ValueError(
            f"ACERVO_SOURCE must name the origin whose fields the staging transform reads. Available: {sorted(SOURCES)}"
        )
    try:
        return SOURCES[resolved]
    except KeyError:
        raise ValueError(f"Unknown source {resolved!r}. Available: {sorted(SOURCES)}") from None


def get_adapters(code: str | None = None) -> OriginAdapters:
    """
    The active origin's ports: the explicit code wins, then ``ACERVO_SOURCE``.

    The selector is the one :func:`get_source_schema` already uses, deliberately: an origin is one
    declaration, and naming it from the command line must not be a second way of choosing a source
    that can disagree with the vocabulary the transform reads. There is no default here either.
    """
    resolved = code or settings.ACERVO_SOURCE
    if not resolved:
        raise ValueError(f"ACERVO_SOURCE must name the origin to read. Available: {sorted(ADAPTERS)}")
    try:
        factory = ADAPTERS[resolved]
    except KeyError:
        raise ValueError(f"Unknown source {resolved!r}. Available: {sorted(ADAPTERS)}") from None
    return factory()
