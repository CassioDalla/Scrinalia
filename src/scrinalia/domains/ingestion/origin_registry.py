"""The definitions of the origins this package ships, without importing their adapters.

This module is the cheap half of the registry: names, labels, kinds, the shape of each origin's
configuration and the metadata the screen renders. It deliberately imports no adapter (the PMC
module drags ``requests`` and ``bs4``; the API process imports this module on every panel read).

The *vocabulary* of an origin still lives next to its adapter, in a ``SourceSchema``. The split is
the same one ADR 0008 draws: a label is the site's payload key and stays with the code that reads
it; the lifecycle — enabled, URLs, agenda — is data and lives in ``ingestion_origins``.

Adding an origin is a module with its adapter and schema, an entry here, and a row in the table. The
staging transform and the ingestion job do not change.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from scrinalia.core.i18n import t
from scrinalia.domains.ingestion.exceptions import OriginNotFoundError


class OriginKind(StrEnum):
    """How an origin produces records; the job branches on the kind, never on a site's name."""

    SCRAPER = "SCRAPER"
    MANUAL = "MANUAL"
    #: A batch of rows uploaded from the screen. There is no adapter and no site; the import route
    #: stages the rows itself, and an ``ingestion`` run of this origin only retries leftovers.
    CSV = "CSV"


#: The control a configuration field needs on the screen.
ConfigFieldKind = Literal["text", "number", "boolean"]


@dataclass(frozen=True)
class OriginConfigField:
    """
    One field of an origin's configuration, as the screen renders it.

    It is metadata *about* the Pydantic model beside it, not a second validation: the model is what
    the API validates. The pair is pinned by a test (every field here exists in the model and every
    model field is described here), so a new URL cannot become a JSON box nobody knows how to fill.
    """

    name: str
    label: str
    help: str
    kind: ConfigFieldKind = "text"
    required: bool = False
    default: object | None = None


class PmcOriginConfig(BaseModel):
    """
    What the reference scraper needs, as the operator configures it.

    ``base_url`` and ``detail_url`` may be empty: the adapter then falls back to the
    ``PUBLIC_SCRAPE_*`` settings, which is what keeps an existing ``.env`` working after the upgrade
    (ADR 0016). A *new* origin has no such fallback — the empty value is refused by its own builder.
    """

    base_url: str | None = Field(default=None, description="URL da listagem paginada da origem.")
    detail_url: str | None = Field(default=None, description="Prefixo da página de detalhe de cada registro.")
    delay_requests: float = Field(default=0.5, ge=0, description="Espera entre requisições, em segundos.")


class ManualOriginConfig(BaseModel):
    """A manual origin has no adapter configuration; the form is its input."""

    pass


class CsvOriginConfig(BaseModel):
    """A CSV origin has no adapter configuration; the uploaded rows are its input."""

    pass


@dataclass(frozen=True)
class OriginSummary:
    """The definition half of an origin: what it is and how its configuration is shaped."""

    code: str
    label: str
    description: str
    kind: OriginKind
    config_model: type[BaseModel]
    config_fields: tuple[OriginConfigField, ...] = ()
    #: Whether the origin is a **source** the operator configures and adds (#206), as opposed to an
    #: input path (the manual form and the CSV import). The page splits on it: the sources have the
    #: lifecycle, the agenda and the run; the entries are shown read-only with their own link. It is
    #: also what the health probe counts, so its number means the same thing as the page's.
    configurable: bool = True


#: The origins the package ships. Insertion order is the order the screen shows; the manual origin
#: comes second on purpose, because it is the one an archivist reaches without an operator.
ORIGINS: Mapping[str, OriginSummary] = {
    "pmc": OriginSummary(
        code="pmc",
        label="Acervo de referência (PMC)",
        description=(
            "Lê a listagem paginada e cada página de detalhe do site de referência. É a origem que a "
            "instalação já tinha antes de a ingestão ser plural."
        ),
        kind=OriginKind.SCRAPER,
        config_model=PmcOriginConfig,
        config_fields=(
            OriginConfigField(
                name="base_url",
                label="URL da listagem",
                help="Endereço da listagem paginada. Vazio usa PUBLIC_SCRAPE_URL.",
                required=False,
            ),
            OriginConfigField(
                name="detail_url",
                label="URL do detalhe",
                help="Prefixo da página de detalhe. Vazio usa PUBLIC_SCRAPE_DETAIL_URL.",
                required=False,
            ),
            OriginConfigField(
                name="delay_requests",
                label="Espera entre requisições (s)",
                help="Intervalo de cortesia entre duas requisições ao mesmo site.",
                kind="number",
                required=False,
                default=0.5,
            ),
        ),
    ),
    "manual": OriginSummary(
        code="manual",
        label="Entrada manual",
        description=(
            "Um registro digitado por uma pessoa. Não é uma aprovação: entra no mesmo staging e na "
            "mesma fila de IA das outras origens."
        ),
        kind=OriginKind.MANUAL,
        config_model=ManualOriginConfig,
        configurable=False,
    ),
    "csv": OriginSummary(
        code="csv",
        label="Importação CSV",
        description=(
            "Um arquivo CSV lido no navegador e enviado como linhas. Não passa pelo storage: entra "
            "no mesmo staging e na mesma fila de IA das outras origens, com o resultado por linha."
        ),
        kind=OriginKind.CSV,
        config_model=CsvOriginConfig,
        configurable=False,
    ),
}


def get_origin_summary(code: str | None) -> OriginSummary:
    """
    The definition of one origin, or a sentence naming the ones the package has.

    There is **no default**: a code is always named by the row that is acting, never inherited from
    an environment variable. That is the ADR 0008 rule one layer down.
    """
    if not code:
        raise OriginNotFoundError(t("Informe a origem. Disponíveis: {origins}.", origins=sorted(ORIGINS)))
    try:
        return ORIGINS[code]
    except KeyError:
        raise OriginNotFoundError(
            t("Origem '{code}' não existe. Disponíveis: {origins}.", code=code, origins=sorted(ORIGINS))
        ) from None
