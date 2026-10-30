"""The open dataset contract: the field map, the manifest and the committed artifacts.

The dataset is the first export a consumer this installation does not control reads (ADR 0024), so
its schema is a contract in the same sense the OpenAPI document is: generated from the code,
committed, and compared by a test. The field map is the metadata-standard answer made auditable —
every exported field names its ISAD(G) element, or says why it has none.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from scrinalia.domains.archive.schemas.public_projection import PublicDocumentSummary
from scrinalia.domains.diffusion.dataset_contract import (
    DATASET_FIELDS,
    DATASET_SCHEMA_VERSION,
    DatasetField,
    DatasetFieldKind,
    DatasetLicense,
    DatasetLicenseId,
    DatasetManifest,
    assert_schema_version_is_the_literal,
    contract_directory,
    contract_documents,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMITTED = REPO_ROOT / "packages" / "dataset-contract" / contract_directory()


# ==========================================
# THE FIELD MAP: THE EXACT PARTITION
# ==========================================


def test_the_field_map_is_an_exact_partition_of_the_public_projection() -> None:
    """
    A field added to the projection without a line in the map fails here.

    The same invariant ``NOT_PUBLIC_FIELDS`` enforces on the public side, one layer out: the map
    cannot quietly lag the schema, and a field cannot be exported without a documented provenance.
    """
    mapped = {field.name for field in DATASET_FIELDS}
    projected = set(PublicDocumentSummary.model_fields)

    assert mapped == projected, (
        f"O mapa de campos e a projeção divergem. Sem classificação: {sorted(projected - mapped)}; "
        f"sem campo na projeção: {sorted(mapped - projected)}."
    )


def test_the_field_map_has_no_duplicate_name() -> None:
    names = [field.name for field in DATASET_FIELDS]
    assert len(names) == len(set(names))


def test_an_isad_g_field_names_an_element_and_the_others_do_not() -> None:
    for field in DATASET_FIELDS:
        if field.kind is DatasetFieldKind.ISAD_G:
            assert field.isad_g, f"{field.name} is ISAD(G) but names no element"
        else:
            assert field.isad_g is None, f"{field.name} names an element but is {field.kind}"


def test_the_four_widened_fields_name_their_isad_elements() -> None:
    """The decision of 2026-10-30 (#214, ADR 0024), pinned by element and not by prose."""
    by_name = {field.name: field for field in DATASET_FIELDS}
    assert by_name["date_expression"].isad_g == "3.1.3"
    assert by_name["level_code"].isad_g == "3.1.4"
    assert by_name["dimension_support"].isad_g == "3.1.5"
    assert by_name["access_conditions"].isad_g == "4.1"


def test_the_storage_uri_is_not_part_of_the_contract() -> None:
    """An ``s3://bucket/key`` is not an address a dataset consumer can read (#198)."""
    assert "storage_thumbnail_uri" not in PublicDocumentSummary.model_fields
    assert "storage_thumbnail_uri" not in json.dumps(contract_documents()["documents.schema.json"])


# ==========================================
# THE COMMITTED ARTIFACTS
# ==========================================


def test_the_committed_contract_is_current() -> None:
    """The committed files are what the code generates now, not what it generated once."""
    for name, document in contract_documents().items():
        committed = json.loads((COMMITTED / name).read_text(encoding="utf-8"))
        assert committed == document, (
            f"packages/dataset-contract/{contract_directory()}/{name} está desatualizado. "
            "Rode: uv run python -m scrinalia.domains.diffusion.dump_dataset_contract"
        )


def test_the_contract_version_and_its_directory_agree() -> None:
    assert DATASET_SCHEMA_VERSION == "1.0"
    assert contract_directory() == "v1"
    assert_schema_version_is_the_literal()


def test_the_generated_record_schema_is_closed() -> None:
    """The projection is the complete set of fields; the schema says so."""
    schema = contract_documents()["documents.schema.json"]
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == set(PublicDocumentSummary.model_fields)


# ==========================================
# THE MANIFEST
# ==========================================


def _manifest(**overrides: Any) -> DatasetManifest:
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "snapshot_id": "a" * 64,
        "previous_snapshot_id": None,
        "generated_at": "2026-10-30T12:00:00Z",
        "record_count": 0,
        "artifacts": [
            {
                "format": "ndjson",
                "path": "documents.ndjson",
                "bytes": 0,
                "sha256": "b" * 64,
                "records": 0,
            }
        ],
        "removals": [],
        "license": {
            "id": "CC-BY-4.0",
            "name": "Creative Commons Atribuição 4.0 Internacional",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "Acervo de teste, CC BY 4.0",
        },
        "institution": {"name": "Instituição de teste"},
        "software": {
            "name": "Scrinalia",
            "version": "1.8.0",
            "license": "AGPL-3.0-only",
            "license_url": "https://www.gnu.org/licenses/agpl-3.0.html",
            "source_url": "https://github.com/CassioDalla/Scrinalia",
        },
        "api_url": None,
        "openapi_url": None,
    }
    data.update(overrides)
    return DatasetManifest(**data)


def test_the_manifest_round_trips_through_json() -> None:
    manifest = _manifest()
    assert DatasetManifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_the_manifest_refuses_an_unknown_key() -> None:
    with pytest.raises(ValidationError):
        _manifest(extra="a key the writer invented")


@pytest.mark.parametrize("license_id", ["CC-BY-4.0", "CC-BY-SA-4.0"])
def test_the_attribution_licenses_require_the_tasl_line(license_id: DatasetLicenseId) -> None:
    with pytest.raises(ValidationError):
        DatasetLicense(id=license_id, name="Creative Commons")


def test_cc0_does_not_require_attribution() -> None:
    license_ = DatasetLicense(id="CC0-1.0", name="CC0 1.0 Universal")
    assert license_.attribution is None


def test_a_custom_license_states_its_url_and_attribution() -> None:
    with pytest.raises(ValidationError):
        DatasetLicense(id="custom", name="Licença institucional")


def test_the_first_snapshot_has_no_previous_id_and_no_removal() -> None:
    manifest = _manifest()
    assert manifest.previous_snapshot_id is None
    assert manifest.removals == []


def test_a_removal_is_a_description_id() -> None:
    manifest = _manifest(removals=["node_0123456789abcdef"], previous_snapshot_id="c" * 64)
    assert manifest.removals == ["node_0123456789abcdef"]


def test_a_field_map_entry_is_a_frozen_value() -> None:
    """``DatasetField`` is internal and computed once; it is not a boundary to validate."""
    field = DatasetField(
        name="level_code",
        kind=DatasetFieldKind.ISAD_G,
        isad_g="3.1.4",
        cardinality="one",
        description="x",
    )
    with pytest.raises(AttributeError):
        field.name = "other"  # type: ignore[misc]
