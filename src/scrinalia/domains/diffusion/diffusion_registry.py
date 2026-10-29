"""The definitions of the diffusion channels this package ships, without their adapters.

This module is the cheap half of the registry, the mirror of
``domains/ingestion/origin_registry.py``: names, labels, capabilities, the Pydantic model of each
channel's configuration and the metadata the operator screen renders. It deliberately imports no
adapter, so the API process can list the channels on every panel read.

A channel is a definition in code plus a row in ``diffusion_channels`` (ADR 0023). Adding one is a
module with its adapter, an entry here and a row; the page and the run do not change.

The ``public_site`` channel is the first, and it is ``LIVE``: it has no run, and its job is to say
whether the built-in public app exists for this installation and what it is called. The dataset and
AtoM are ``EXPORT`` channels and land with their own adapters (#214); the registry only offers
channels that work.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from scrinalia.core.i18n import t
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
        """An empty value is a cleared contact; a non-empty one has to look like an email."""
        if value is None or not value.strip():
            return None
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("informe um e-mail de contato válido")
        return value


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


#: The channels the package ships. Insertion order is the order the add picker shows.
CHANNELS: Mapping[str, DiffusionChannelSummary] = {
    "public_site": DiffusionChannelSummary(
        code="public_site",
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
