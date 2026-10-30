"""The diffusion registry: the definitions and the configuration-field pin.

The registry is cheap on purpose (it imports no adapter), and the screen renders exactly the fields
the channel's own model declares. A field that exists here and not in the model would be a control
that saves nothing; a field in the model and not here would be a JSON box nobody knows how to fill.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from scrinalia.domains.diffusion.diffusion_registry import (
    CHANNELS,
    DATASET_CODE,
    DatasetConfig,
    DiffusionCapability,
    PublicSiteConfig,
    get_channel_summary,
)
from scrinalia.domains.diffusion.exceptions import DiffusionChannelNotFoundError


def test_the_registry_ships_the_live_site_and_the_dataset_export() -> None:
    assert list(CHANNELS) == ["public_site", DATASET_CODE]

    site = CHANNELS["public_site"]
    assert site.capability is DiffusionCapability.LIVE
    assert site.config_model is PublicSiteConfig
    assert site.adapter is None

    dataset = CHANNELS[DATASET_CODE]
    assert dataset.capability is DiffusionCapability.EXPORT
    assert dataset.config_model is DatasetConfig
    assert dataset.adapter == "scrinalia.domains.diffusion.dataset_writer"


@pytest.mark.parametrize("code", ["public_site", DATASET_CODE])
def test_the_config_fields_are_exactly_the_model_fields(code: str) -> None:
    summary = CHANNELS[code]
    described = {field.name for field in summary.config_fields}
    assert described == set(summary.config_model.model_fields), (
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


def _dataset_config(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "dataset_title": "Acervo de teste",
        "license_id": "CC-BY-4.0",
        "attribution": "Acervo de teste, CC BY 4.0",
    }
    data.update(overrides)
    return data


def test_the_dataset_config_accepts_the_defaults() -> None:
    config = DatasetConfig.model_validate(_dataset_config())

    assert config.formats == ("json", "ndjson", "csv")
    assert config.retention == 2
    assert config.destination_path is None


def test_the_dataset_config_requires_a_title_and_a_license() -> None:
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate({"license_id": "CC0-1.0"})
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate({"dataset_title": "Acervo"})


def test_the_dataset_config_requires_at_least_one_format() -> None:
    with pytest.raises(ValidationError, match="pelo menos um formato"):
        DatasetConfig.model_validate(_dataset_config(format_json=False, format_ndjson=False, format_csv=False))


def test_the_dataset_config_formats_keep_the_documented_order() -> None:
    config = DatasetConfig.model_validate(_dataset_config(format_json=False))

    assert config.formats == ("ndjson", "csv")


def test_the_dataset_destination_must_be_absolute() -> None:
    with pytest.raises(ValidationError, match="caminho absoluto"):
        DatasetConfig.model_validate(_dataset_config(destination_path="dados"))

    config = DatasetConfig.model_validate(_dataset_config(destination_path="/srv/dataset"))

    assert config.destination_path == "/srv/dataset"


def test_the_dataset_license_requires_its_terms() -> None:
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(_dataset_config(attribution=None))
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(_dataset_config(license_id="custom", license_name="Licença"))
    complete = DatasetConfig.model_validate(
        _dataset_config(
            license_id="custom",
            license_name="Licença institucional",
            license_url="https://example.org/licenca",
        )
    )

    assert complete.as_license().name == "Licença institucional"


def test_the_known_license_carries_its_canonical_name_and_url() -> None:
    license_ = DatasetConfig.model_validate(_dataset_config()).as_license()

    assert license_.name == "Creative Commons Attribution 4.0 International"
    assert str(license_.url) == "https://creativecommons.org/licenses/by/4.0/"


def test_cc0_does_not_require_attribution() -> None:
    config = DatasetConfig.model_validate(_dataset_config(license_id="CC0-1.0", attribution=None))

    assert config.as_license().attribution is None
