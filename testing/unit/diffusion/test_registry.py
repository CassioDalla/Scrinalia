"""The diffusion registry: the definitions and the configuration-field pin.

The registry is cheap on purpose (it imports no adapter), and the screen renders exactly the fields
the channel's own model declares. A field that exists here and not in the model would be a control
that saves nothing; a field in the model and not here would be a JSON box nobody knows how to fill.
"""

import pytest
from pydantic import ValidationError

from scrinalia.domains.diffusion.diffusion_registry import (
    CHANNELS,
    DiffusionCapability,
    PublicSiteConfig,
    get_channel_summary,
)
from scrinalia.domains.diffusion.exceptions import DiffusionChannelNotFoundError


def test_the_public_site_is_the_only_shipped_channel_for_now() -> None:
    assert list(CHANNELS) == ["public_site"]
    summary = CHANNELS["public_site"]
    assert summary.capability is DiffusionCapability.LIVE
    assert summary.config_model is PublicSiteConfig


def test_the_config_fields_are_exactly_the_model_fields() -> None:
    summary = CHANNELS["public_site"]
    described = {field.name for field in summary.config_fields}
    assert described == set(PublicSiteConfig.model_fields), (
        "a tela renderiza um campo que o modelo não tem, ou o modelo ganhou um campo sem controle"
    )


def test_an_unknown_channel_names_the_known_ones() -> None:
    with pytest.raises(DiffusionChannelNotFoundError, match="public_site"):
        get_channel_summary("nope")


def test_an_empty_code_is_a_refusal_and_not_a_default() -> None:
    with pytest.raises(DiffusionChannelNotFoundError):
        get_channel_summary("")


def test_the_public_site_config_accepts_a_complete_identity() -> None:
    config = PublicSiteConfig.model_validate(
        {
            "site_title": "Acervo",
            "site_description": "Descrição do acervo.",
            "institution_name": "Instituição",
            "contact_email": "acervo@example.org",
            "logo_url": "https://example.org/logo.png",
            "public_base_url": "https://example.org",
            "locale": "pt-BR",
            "allow_indexing": False,
        }
    )

    dumped = config.model_dump(mode="json", exclude_none=True)

    assert dumped["logo_url"] == "https://example.org/logo.png"
    assert dumped["public_base_url"] == "https://example.org/"
    assert dumped["allow_indexing"] is False


def test_the_public_site_config_requires_a_title() -> None:
    with pytest.raises(ValidationError):
        PublicSiteConfig.model_validate({})


def test_the_public_site_config_refuses_a_bad_email() -> None:
    with pytest.raises(ValidationError):
        PublicSiteConfig.model_validate({"site_title": "Acervo", "contact_email": "nao-e-um-email"})


def test_the_public_site_config_refuses_a_bad_url_and_an_unknown_field() -> None:
    with pytest.raises(ValidationError):
        PublicSiteConfig.model_validate({"site_title": "Acervo", "public_base_url": "nao-e-uma-url"})
    with pytest.raises(ValidationError):
        PublicSiteConfig.model_validate({"site_title": "Acervo", "unknown_field": "x"})
