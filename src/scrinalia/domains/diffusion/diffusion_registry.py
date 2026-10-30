"""The definitions of the diffusion channels this package ships, without their adapters.

This module is the cheap half of the registry, the mirror of
``domains/ingestion/origin_registry.py``: names, labels, capabilities, the Pydantic model of each
channel's configuration and the metadata the operator screen renders. It deliberately imports no
adapter, so the API process can list the channels on every panel read.

A channel is a definition in code plus a row in ``diffusion_channels`` (ADR 0023). Adding one is a
module with its adapter, an entry here and a row; the page and the run do not change.

The ``public_site`` channel is the first, and it is ``LIVE``: it has no run, and its job is to say
whether the built-in public app exists for this installation and what it is called. The ``dataset``
channel is the first ``EXPORT``: its adapter writes the open dataset snapshot (ADR 0024). AtoM is a
future adapter; the registry only offers channels that work.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator, model_validator

from scrinalia.core.i18n import t
from scrinalia.domains.diffusion.dataset_contract import DATASET_LICENSES, DatasetLicense, DatasetLicenseId
from scrinalia.domains.diffusion.exceptions import DiffusionAdapterMissingError, DiffusionChannelNotFoundError

if TYPE_CHECKING:
    from scrinalia.domains.diffusion.ports import DiffusionAdapter


class DiffusionCapability(StrEnum):
    """How a channel leaves the archive: read live on every request, or exported by a run."""

    LIVE = "LIVE"
    EXPORT = "EXPORT"


#: The control a configuration field needs on the screen.
ConfigFieldKind = Literal["text", "number", "boolean"]


@dataclass(frozen=True)
class DiffusionConfigField:
    """
    One field of a channel's configuration, as the operator screen renders it.

    It is metadata *about* the Pydantic model beside it, not a second validation: the model is what
    the API validates. A test pins the pair (every field here exists in the model and every model
    field is described here), so a new setting cannot become a JSON box nobody knows how to fill.
    """

    name: str
    label: str
    help: str
    kind: ConfigFieldKind = "text"
    required: bool = False
    default: object | None = None


def _normalized_email(value: str | None) -> str | None:
    """An empty value is a cleared contact; a non-empty one has to look like an email."""
    if value is None or not value.strip():
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("informe um e-mail de contato válido")
    return value


class PublicSiteConfig(BaseModel):
    """
    The presentation identity of the built-in public site (#46): no records, no secrets.

    The site app reads it before its first document query. ``site_title`` is the one required field;
    the rest may be filled as the institution prepares the site, and a channel can be configured
    before the app is deployed — the operator sees the configured address, not a false "published".
    """

    model_config = ConfigDict(extra="forbid")

    site_title: str = Field(
        min_length=1,
        max_length=200,
        description="O título que o site público mostra no cabeçalho.",
    )
    site_description: str | None = Field(
        default=None,
        max_length=500,
        description="Uma frase sobre o acervo, para a página inicial do site.",
    )
    institution_name: str | None = Field(
        default=None,
        max_length=200,
        description="O nome da instituição responsável pelo acervo.",
    )
    contact_email: str | None = Field(
        default=None,
        max_length=254,
        description="O endereço que o visitante usa para falar com a instituição.",
    )
    #: The external URL; the model's type validates it, so a typo is a 422 on save.
    logo_url: HttpUrl | None = None
    locale: Literal["pt-BR", "en"] = Field(
        default="pt-BR",
        description="O idioma do site público. O aplicativo pode oferecer apenas pt-BR primeiro.",
    )
    #: The canonical address used by the "Ver site" link, the sitemap and the canonical links.
    public_base_url: HttpUrl | None = None
    allow_indexing: bool = Field(
        default=True,
        description="Se os buscadores podem indexar o site público.",
    )

    @field_validator("contact_email")
    @classmethod
    def _valid_contact_email(cls, value: str | None) -> str | None:
        """The public site's contact, validated by the same rule as the dataset's."""
        return _normalized_email(value)


class DatasetConfig(BaseModel):
    """
    The open dataset's configuration: where the snapshot goes, what it carries and under which terms.

    The **data** license is required and has no default: a package without terms is not a dataset the
    institution can defend, and the run refuses before writing. The known licenses carry their
    canonical name and URL (:data:`DATASET_LICENSES`); ``custom`` asks for the institution's own.

    ``destination_path`` is optional on purpose — an operator can configure the channel and choose the
    directory later — but a run without it refuses with a sentence. It must be absolute: a relative
    path would resolve to the runner's working directory, which is not a fact the operator can see.

    The formats are three booleans and not a list because the generic configuration renderer knows
    text, number and boolean; a multi-select would be a second control to implement for one channel.
    At least one is required.
    """

    model_config = ConfigDict(extra="forbid")

    dataset_title: str = Field(min_length=1, max_length=200, description="O nome do conjunto de dados.")
    dataset_description: str | None = Field(
        default=None, max_length=1000, description="Uma frase sobre o conjunto, para o README do pacote."
    )
    destination_path: str | None = Field(
        default=None,
        max_length=500,
        description="O diretório absoluto onde o snapshot é escrito; a execução recusa sem ele.",
    )
    retention: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Quantos snapshots são mantidos no destino; o atual nunca é apagado.",
    )
    format_json: bool = Field(default=True, description="Escreve documents.json.")
    format_ndjson: bool = Field(default=True, description="Escreve documents.ndjson.")
    format_csv: bool = Field(default=True, description="Escreve documents.csv.")
    license_id: DatasetLicenseId = Field(description="CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0 ou custom.")
    license_name: str | None = Field(default=None, max_length=200, description="Só para a licença custom.")
    license_url: HttpUrl | None = Field(
        default=None, description="Só para a licença custom; as conhecidas têm URL canônica."
    )
    attribution: str | None = Field(
        default=None,
        max_length=2000,
        description="A linha TASL que o consumidor deve exibir; obrigatória em CC BY e CC BY-SA.",
    )
    institution_name: str | None = Field(
        default=None, max_length=200, description="Sem ela, usa a instituição do site público."
    )
    contact_email: str | None = Field(default=None, max_length=254, description="O contato que o pacote publica.")
    api_base_url: HttpUrl | None = Field(
        default=None,
        description="A URL pública desta instalação, para os links do manifesto; sem ela, usa a do site público.",
    )

    @field_validator("destination_path")
    @classmethod
    def _destination_is_absolute(cls, value: str | None) -> str | None:
        """A relative destination is a path the runner resolves, not the one the operator chose."""
        if value is not None and not Path(value).is_absolute():
            raise ValueError("informe um caminho absoluto para o destino")
        return value

    @field_validator("contact_email")
    @classmethod
    def _valid_contact_email(cls, value: str | None) -> str | None:
        """The same rule the public site's contact follows."""
        return _normalized_email(value)

    @property
    def formats(self) -> tuple[Literal["json", "ndjson", "csv"], ...]:
        """The formats this configuration writes, in the order the manifest lists them."""
        chosen: list[Literal["json", "ndjson", "csv"]] = []
        if self.format_json:
            chosen.append("json")
        if self.format_ndjson:
            chosen.append("ndjson")
        if self.format_csv:
            chosen.append("csv")
        return tuple(chosen)

    def as_license(self) -> DatasetLicense:
        """
        The manifest's license, from the configured id and the canonical terms.

        Constructing :class:`DatasetLicense` is what validates the pair: the CC licenses demand the
        TASL attribution, and a custom license demands its name, URL and attribution. The rules live
        there once, and this method is the only place that translates the flat form into them.
        """
        terms = DATASET_LICENSES.get(self.license_id)
        return DatasetLicense(
            id=self.license_id,
            name=terms.name if terms is not None else (self.license_name or ""),
            url=self.license_url
            if self.license_url is not None
            else (HttpUrl(terms.url) if terms is not None else None),
            attribution=self.attribution,
        )

    @model_validator(mode="after")
    def _coherent(self) -> DatasetConfig:
        """At least one format, and a license whose terms are complete."""
        if not self.formats:
            raise ValueError("escolha pelo menos um formato de saída: JSON, NDJSON ou CSV")
        if self.license_id == "custom" and not self.license_name:
            raise ValueError("informe o nome da licença personalizada")
        try:
            self.as_license()
        except ValidationError as exc:
            raise ValueError(exc.errors()[0]["msg"]) from exc
        return self


@dataclass(frozen=True)
class DiffusionChannelSummary:
    """The definition half of a channel: what it is and how its configuration is shaped."""

    code: str
    label: str
    description: str
    capability: DiffusionCapability
    config_model: type[BaseModel]
    config_fields: tuple[DiffusionConfigField, ...] = ()
    #: The module that writes this channel's export, or ``None`` when the package ships the
    #: definition without an adapter yet. It is a **string** so this module imports no adapter: the
    #: API lists the channels on every panel read and must not pull a dataset writer into a process
    #: that never exports. ``resolve_adapter`` imports it on the run that needs it.
    adapter: str | None = None


#: The built-in site's code. The one name the public surface, the coverage counts and the
#: public site's identity read; a literal here and in four callers would drift.
PUBLIC_SITE_CODE = "public_site"

#: The open dataset's code: the first ``EXPORT`` channel and the one the writer reads.
DATASET_CODE = "dataset"

#: The channels the package ships. Insertion order is the order the add picker shows.
CHANNELS: Mapping[str, DiffusionChannelSummary] = {
    PUBLIC_SITE_CODE: DiffusionChannelSummary(
        code=PUBLIC_SITE_CODE,
        label="Site público",
        description=(
            "O site público embutido: a identidade que o aplicativo lê antes da primeira consulta de "
            "documentos. O aplicativo é uma superfície separada (#46); habilitar o canal não o instala."
        ),
        capability=DiffusionCapability.LIVE,
        config_model=PublicSiteConfig,
        config_fields=(
            DiffusionConfigField(
                name="site_title",
                label="Título do site",
                help="O nome que o site público mostra no cabeçalho.",
                required=True,
            ),
            DiffusionConfigField(
                name="site_description",
                label="Descrição do site",
                help="Uma frase sobre o acervo, para a página inicial do site.",
            ),
            DiffusionConfigField(
                name="institution_name",
                label="Instituição",
                help="O nome da instituição responsável pelo acervo.",
            ),
            DiffusionConfigField(
                name="contact_email",
                label="E-mail de contato",
                help="O endereço que o visitante usa para falar com a instituição.",
            ),
            DiffusionConfigField(
                name="logo_url",
                label="URL do logotipo",
                help="Um endereço externo para o logotipo; o envio de arquivo ainda não existe.",
            ),
            DiffusionConfigField(
                name="locale",
                label="Idioma",
                help="O idioma do site público: pt-BR ou en.",
                default="pt-BR",
            ),
            DiffusionConfigField(
                name="public_base_url",
                label="URL pública",
                help="O endereço canônico do site, usado nos links e no mapa do site.",
            ),
            DiffusionConfigField(
                name="allow_indexing",
                label="Permitir indexação",
                help="Se os buscadores podem indexar o site.",
                kind="boolean",
                default=True,
            ),
        ),
    ),
    DATASET_CODE: DiffusionChannelSummary(
        code=DATASET_CODE,
        label="Conjunto de dados",
        description=(
            "Um snapshot do acervo publicado neste canal, em JSON, NDJSON e CSV, com manifesto, "
            "licença de dados e mapa de campos, para um site próprio hospedar ou outro sistema importar."
        ),
        capability=DiffusionCapability.EXPORT,
        config_model=DatasetConfig,
        config_fields=(
            DiffusionConfigField(
                name="dataset_title",
                label="Título do conjunto",
                help="O nome que o pacote e o README mostram.",
                required=True,
            ),
            DiffusionConfigField(
                name="dataset_description",
                label="Descrição do conjunto",
                help="Uma frase sobre o conjunto, para o README do pacote.",
            ),
            DiffusionConfigField(
                name="destination_path",
                label="Diretório de destino",
                help="O caminho absoluto onde o snapshot é escrito; a execução recusa sem ele.",
            ),
            DiffusionConfigField(
                name="retention",
                label="Snapshots mantidos",
                help="Quantos snapshots ficam no destino; o atual nunca é apagado.",
                kind="number",
                default=2,
            ),
            DiffusionConfigField(
                name="format_json",
                label="JSON",
                help="Um arquivo documents.json com o envelope e os registros.",
                kind="boolean",
                default=True,
            ),
            DiffusionConfigField(
                name="format_ndjson",
                label="NDJSON",
                help="Um registro por linha, para a ingestão de um site próprio.",
                kind="boolean",
                default=True,
            ),
            DiffusionConfigField(
                name="format_csv",
                label="CSV",
                help="Uma planilha achatada; os campos multivalorados vão como JSON na célula.",
                kind="boolean",
                default=True,
            ),
            DiffusionConfigField(
                name="license_id",
                label="Licença dos dados",
                help="CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0 ou custom. Obrigatória.",
                required=True,
            ),
            DiffusionConfigField(
                name="license_name",
                label="Nome da licença",
                help="Só para a licença custom.",
            ),
            DiffusionConfigField(
                name="license_url",
                label="URL da licença",
                help="Só para a licença custom; as conhecidas têm URL canônica.",
            ),
            DiffusionConfigField(
                name="attribution",
                label="Atribuição",
                help="A linha TASL que o consumidor deve exibir; obrigatória em CC BY e CC BY-SA.",
            ),
            DiffusionConfigField(
                name="institution_name",
                label="Instituição",
                help="Sem ela, usa a instituição do site público.",
            ),
            DiffusionConfigField(
                name="contact_email",
                label="E-mail de contato",
                help="O contato que o pacote publica.",
            ),
            DiffusionConfigField(
                name="api_base_url",
                label="URL pública da API",
                help="Para os links do manifesto; sem ela, usa a URL do site público.",
            ),
        ),
        adapter="scrinalia.domains.diffusion.dataset_writer",
    ),
}


def get_channel_summary(code: str) -> DiffusionChannelSummary:
    """
    The definition of one channel, or a sentence naming the ones the package has.

    There is **no default**: a code is always named by the row that is acting, exactly like the
    origin registry (ADR 0008/0016) one layer out.
    """
    if not code:
        raise DiffusionChannelNotFoundError(t("Informe o canal. Disponíveis: {channels}.", channels=sorted(CHANNELS)))
    try:
        return CHANNELS[code]
    except KeyError:
        raise DiffusionChannelNotFoundError(
            t("Canal de difusão '{code}' não existe. Disponíveis: {channels}.", code=code, channels=sorted(CHANNELS))
        ) from None


def adapter_module(summary: DiffusionChannelSummary) -> str:
    """
    The module that writes this channel, or a refusal that names the channel.

    It is the one definition of "this channel has an adapter": the API's enqueue and the scheduler's
    due check call it without importing anything, and ``resolve_adapter`` imports what it returns.
    A channel the package ships without an adapter cannot export, and the operator reads the
    sentence instead of a run that fails for a reason they cannot fix (#214 ships the first one).
    """
    if summary.adapter is None:
        raise DiffusionAdapterMissingError(t("O canal '{code}' ainda não exporta nesta versão.", code=summary.code))
    return summary.adapter


def resolve_adapter(summary: DiffusionChannelSummary) -> DiffusionAdapter:
    """
    The callable that writes this channel, imported on the run that needs it.

    The definition names the module and this is the only place it is imported, which is what keeps
    the registry cheap: listing the channels never pays for an adapter.
    """
    return cast("DiffusionAdapter", import_module(adapter_module(summary)).execute)
