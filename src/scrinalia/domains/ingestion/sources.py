"""
Which origin a deployment reads, and where each origin's vocabulary is declared.

The registry exists for the same reason ``core/language`` does: an origin is selected by name and
resolved once, so a second one is an entry plus a module instead of a branch inside the transform.
``ACERVO_SOURCE`` names it, and the resolution **fails fast** when it is unset — a staging run with
no field map would file every column as unknown, and an empty staging row is worse than an error.

The concrete schemas live next to the adapters that read those sites: an origin's vocabulary is only
meaningful together with the code that extracts it.
"""

from functools import lru_cache

from scrinalia.core.config import settings
from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA
from scrinalia.domains.ingestion.ports import SourceSchema

#: Every origin the package ships. Adding one is adding an entry here and a schema next to its
#: adapter — and, when plural ingestion arrives, a row naming the origin on each raw record.
SOURCES: dict[str, SourceSchema] = {PMC_SOURCE_SCHEMA.code: PMC_SOURCE_SCHEMA}


@lru_cache
def get_source_schema(code: str | None = None) -> SourceSchema:
    """
    The active origin's vocabulary: the explicit code wins, then ``ACERVO_SOURCE``.

    There is **no default**. A fallback would make an installation that never declared its origin
    read the reference site's labels, which is the "the default is Curitiba" defect ADR 0008 removed
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
