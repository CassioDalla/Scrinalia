"""The runtime half of the origin registry: the adapter, the schema and the validated config.

This module imports the concrete adapters, which is why it is not on the API's import path: the
catalogue reads :mod:`origin_registry` (cheap) and the worker resolves this module only when an
ingestion run actually executes. The split is the same one the worker catalogue makes for the AI
axes — the metadata is read by the panel, the heavy implementation only by the run.

There is **no default origin**. A code is always named by the row that is acting; the fallback the
reference adapter still accepts is a fallback for its *URLs* (``PUBLIC_SCRAPE_*``), not for the
origin's identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from scrinalia.core.config import settings
from scrinalia.core.i18n import t
from scrinalia.domains.ingestion.exceptions import InvalidOriginConfigError, OriginNotFoundError
from scrinalia.domains.ingestion.models import IngestionOrigin
from scrinalia.domains.ingestion.origin_registry import OriginKind, OriginSummary, get_origin_summary
from scrinalia.domains.ingestion.ports import OriginAdapters, SourceConfig, SourceSchema


@dataclass(frozen=True)
class OriginDefinition:
    """Everything a run of one origin needs: its definition, its config, its schema and its ports."""

    summary: OriginSummary
    config: BaseModel
    schema: SourceSchema
    adapters: OriginAdapters


def _row_config(code: str, db_session: Session | None, config: dict[str, Any] | None) -> dict[str, Any]:
    """The configuration the caller named, or the row's; a missing row is a refusal, not a default."""
    if config is not None:
        return config
    if db_session is None:
        return {}
    row = db_session.get(IngestionOrigin, code)
    if row is None:
        raise OriginNotFoundError(
            t(
                "A origem '{code}' não está registrada em ingestion_origins. Rode a migração 44 e configure-a na tela de ingestão.",
                code=code,
            )
        )
    return dict(row.config or {})


def _validated_config(summary: OriginSummary, raw: dict[str, Any]) -> BaseModel:
    """Validates the origin's own configuration model; a bad field is a sentence, not a 500."""
    try:
        return summary.config_model.model_validate(raw)
    except Exception as exc:
        raise InvalidOriginConfigError(
            t("Configuração inválida da origem '{code}': {exc}", code=summary.code, exc=exc)
        ) from exc


def get_origin_definition(
    code: str,
    db_session: Session | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> OriginDefinition:
    """
    Resolves one origin's definition, config, vocabulary and ports.

    The manual origin has no ports: its input is the form, and the manual service writes the raw
    record itself. The reference scraper builds one adapter object that implements both phases; a
    future CSV adapter can implement discovery only, and ``OriginAdapters`` already answers that
    shape with a sentence instead of an ``AttributeError``.
    """
    summary = get_origin_summary(code)
    validated = _validated_config(summary, _row_config(code, db_session, config))

    if summary.kind is OriginKind.MANUAL:
        from scrinalia.domains.ingestion.adapters.manual import MANUAL_SOURCE_SCHEMA

        return OriginDefinition(
            summary=summary,
            config=validated,
            schema=MANUAL_SOURCE_SCHEMA,
            adapters=OriginAdapters(code=code),
        )

    if summary.kind is OriginKind.CSV:
        from scrinalia.domains.ingestion.adapters.csv import CSV_SOURCE_SCHEMA

        # No ports: the file is parsed in the browser and the import route writes and stages the
        # rows itself. The schema is still this origin's, so the staging transform learns no site.
        return OriginDefinition(
            summary=summary,
            config=validated,
            schema=CSV_SOURCE_SCHEMA,
            adapters=OriginAdapters(code=code),
        )

    if summary.kind is OriginKind.SCRAPER:
        # Imported here, not at module level: ``requests``/``bs4`` are the adapter's, not the API's.
        from scrinalia.domains.ingestion.adapters.pmc_scraper import PMC_SOURCE_SCHEMA, PMCScraperAdapter

        pmc_config = validated
        base_url = getattr(pmc_config, "base_url", None) or settings.PUBLIC_SCRAPE_URL
        detail_url = getattr(pmc_config, "detail_url", None) or settings.PUBLIC_SCRAPE_DETAIL_URL
        if not base_url or not detail_url:
            raise InvalidOriginConfigError(
                t(
                    "A origem '{code}' precisa de base_url e detail_url (ou de PUBLIC_SCRAPE_URL e PUBLIC_SCRAPE_DETAIL_URL no ambiente).",
                    code=code,
                )
            )
        adapter = PMCScraperAdapter(
            SourceConfig(
                base_url=str(base_url),
                detail_url=str(detail_url),
                delay_requests=float(getattr(pmc_config, "delay_requests", 0.5)),
            )
        )
        return OriginDefinition(
            summary=summary,
            config=pmc_config,
            schema=PMC_SOURCE_SCHEMA,
            adapters=OriginAdapters(code=code, discovery=adapter, detail=adapter),
        )

    raise OriginNotFoundError(
        t("A origem '{code}' declara um tipo que este pacote não conhece: {kind}.", code=code, kind=summary.kind)
    )
