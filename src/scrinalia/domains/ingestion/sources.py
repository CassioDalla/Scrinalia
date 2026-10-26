"""
The origin-facing facade: one vocabulary and one pair of ports, selected by an explicit code.

The definitions live in :mod:`origin_registry` (cheap metadata) and :mod:`origins` (the runtime,
with the adapters). This module is the seam the staging transform and the host CLI already import,
and it keeps two promises the ADR 0008 made:

* **there is no default origin.** ``get_source_schema`` and ``get_adapters`` require a code; the
  ``ACERVO_SOURCE`` fallback is gone, because a fallback would make an installation that never named
  an origin read the reference site's labels. The plural run resolves the schema per record from the
  record's own ``origin_code``; the host command names one explicitly.
* **the vocabulary stays with the adapter.** ``SOURCES`` exposes the schemas the package ships;
  ``get_source_schema`` is a lookup, never a transform.

The ports are resolved through :func:`origins.get_origin_definition`, which reads the origin's row.
A host command that only needs the schema (the staging transform) does not open a row; a command
that needs the adapter does, and answers a missing row with a sentence instead of a default URL.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from scrinalia.domains.ingestion.adapters.csv import CSV_SOURCE_SCHEMA
from scrinalia.domains.ingestion.adapters.manual import MANUAL_SOURCE_SCHEMA
from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA
from scrinalia.domains.ingestion.origin_registry import ORIGINS, get_origin_summary
from scrinalia.domains.ingestion.origins import get_origin_definition
from scrinalia.domains.ingestion.ports import OriginAdapters, SourceSchema

#: Every origin the package ships, by code. The map is the vocabulary half of the registry; the
#: runtime half is ``ADAPTERS`` below, resolved through the same code.
SOURCES: dict[str, SourceSchema] = {
    PMC_SOURCE_SCHEMA.code: PMC_SOURCE_SCHEMA,
    MANUAL_SOURCE_SCHEMA.code: MANUAL_SOURCE_SCHEMA,
    CSV_SOURCE_SCHEMA.code: CSV_SOURCE_SCHEMA,
}

#: Factories kept for the callers that only need the shape of the registry. The real resolution is
#: :func:`get_adapters`, which receives the row (and therefore the operator's configuration).
ADAPTERS: dict[str, Callable[[], OriginAdapters]] = {
    code: (lambda code=code: get_origin_definition(code).adapters) for code in ORIGINS
}


def get_source_schema(code: str | None) -> SourceSchema:
    """
    The vocabulary of one origin, or a refusal naming the ones the package has.

    No fallback: a ``None`` code is a wiring defect, not "use the reference site". The staging
    transform reaches here per record when the caller did not pin a schema, and a record without an
    origin is exactly the case the refusal exists for.
    """
    summary = get_origin_summary(code)
    try:
        return SOURCES[summary.code]
    except KeyError:
        raise ValueError(
            f"A origem '{summary.code}' não declara um SourceSchema. Disponíveis: {sorted(SOURCES)}."
        ) from None


def get_adapters(
    code: str | None,
    db_session: Session | None = None,
    *,
    config: dict | None = None,
) -> OriginAdapters:
    """
    The ports of one origin, resolved from its row (or from an explicit configuration).

    The signature has no default code and no settings read: the adapter is the institution-specific
    piece, and an adapter that decided its own origin would be the defect ADR 0008 removed. A caller
    that has no session (a unit test) may pass ``config`` or rely on the ``PUBLIC_SCRAPE_*`` fallback
    of the reference adapter, which is a fallback for its *URLs*, never for its identity.
    """
    summary = get_origin_summary(code)
    return get_origin_definition(summary.code, db_session, config=config).adapters
