"""The open dataset adapter against the test database: the snapshot, the manifest and the removals.

The adapter is the first export a consumer this installation does not control reads (ADR 0024), so
the tests are about the promises the package makes: the covered set is the coverage view, the files
are deterministic, the manifest carries hashes and terms, a record that leaves the set is listed in
``removals``, and a rerun with the same content writes nothing.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveReviewStatus
from scrinalia.domains.diffusion.dataset_contract import DatasetManifest
from scrinalia.domains.diffusion.dataset_writer import (
    CURRENT_POINTER,
    DATA_FILES,
    SNAPSHOTS_DIR,
    DatasetPreview,
    execute,
    preview,
)
from scrinalia.domains.diffusion.diffusion_registry import DATASET_CODE, DatasetConfig, PublicSiteConfig
from scrinalia.domains.diffusion.exceptions import InvalidDiffusionConfigError
from scrinalia.domains.diffusion.models import DiffusionChannel
from testing.integration.diffusion.publication_helpers import a_channel, a_node, a_scope


def _config(destination: Path | None, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "dataset_title": "Acervo de teste",
        "institution_name": "Instituição de teste",
        "contact_email": "acervo@example.org",
        "license_id": "CC-BY-4.0",
        "attribution": "Acervo de teste, CC BY 4.0",
    }
    if destination is not None:
        data["destination_path"] = str(destination)
    data.update(overrides)
    return data


def _channel(db: Session, config: dict[str, Any], *, enabled: bool = True) -> DiffusionChannel:
    """The dataset's lifecycle row, created once and reconfigured by each test."""
    channel = db.get(DiffusionChannel, DATASET_CODE)
    if channel is None:
        channel = a_channel(db, DATASET_CODE, enabled=enabled)
    channel.enabled = enabled
    channel.config = DatasetConfig.model_validate(config).model_dump(mode="json", exclude_none=True)
    db.commit()
    return channel


def _publish_a_branch(db: Session) -> None:
    """A fundo with two descendants, all approved and covered by one scope on the dataset channel."""
    if db.get(DiffusionChannel, DATASET_CODE) is None:
        a_channel(db, DATASET_CODE)
    a_node(db, "fundo", title="Fundo A")
    a_node(db, "serie", parent_id="fundo", title="Série")
    a_node(db, "item", parent_id="serie", title="Item")
    a_scope(db, "fundo", channel_code=DATASET_CODE)
    db.commit()


def _snapshot_dir(destination: Path) -> Path:
    snapshot_id = (destination / CURRENT_POINTER).read_text(encoding="utf-8").strip()
    return destination / SNAPSHOTS_DIR / snapshot_id


def _manifest(destination: Path) -> DatasetManifest:
    return DatasetManifest.model_validate_json(
        (_snapshot_dir(destination) / "manifest.json").read_text(encoding="utf-8")
    )


# ==========================================
# THE PACKAGE
# ==========================================


def test_a_run_writes_the_three_formats_and_the_manifest(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(tmp_path))

    execute(channel, db_session=db_session)

    snapshot = _snapshot_dir(tmp_path)
    for name in (*DATA_FILES.values(), "manifest.json", "field-map.json", "LICENSE.txt", "README.md"):
        assert (snapshot / name).is_file(), f"{name} não foi escrito"

    manifest = _manifest(tmp_path)
    assert manifest.record_count == 3
    assert manifest.previous_snapshot_id is None
    assert manifest.removals == []
    assert [artifact.format for artifact in manifest.artifacts] == ["json", "ndjson", "csv"]
    assert all(artifact.records == 3 for artifact in manifest.artifacts)
    assert manifest.license.name == "Creative Commons Attribution 4.0 International"
    assert manifest.institution.name == "Instituição de teste"
    assert manifest.software.name == "Scrinalia"

    lines = (snapshot / DATA_FILES["ndjson"]).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["description_id"] for line in lines] == ["fundo", "item", "serie"]

    document = json.loads((snapshot / DATA_FILES["json"]).read_text(encoding="utf-8"))
    assert document["record_count"] == 3
    assert len(document["items"]) == 3
    assert "storage_thumbnail_uri" not in document["items"][0]

    with (snapshot / DATA_FILES["csv"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert "level_code" in rows[0]
    assert "provenance" not in rows[0]


def test_the_manifest_hashes_the_bytes_on_disk(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(tmp_path))

    execute(channel, db_session=db_session)

    for artifact in _manifest(tmp_path).artifacts:
        data = (_snapshot_dir(tmp_path) / artifact.path).read_bytes()
        assert artifact.bytes == len(data)
        assert artifact.sha256 == hashlib.sha256(data).hexdigest()


def test_the_pointer_and_the_manifest_agree(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(tmp_path))

    execute(channel, db_session=db_session)

    pointer = (tmp_path / CURRENT_POINTER).read_text(encoding="utf-8").strip()
    assert pointer == _manifest(tmp_path).snapshot_id


# ==========================================
# DETERMINISM AND IDEMPOTENCY
# ==========================================


def test_a_rerun_with_the_same_set_is_unchanged_and_writes_nothing(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(tmp_path))

    execute(channel, db_session=db_session)
    first = _manifest(tmp_path)
    first_dirs = sorted(path.name for path in (tmp_path / SNAPSHOTS_DIR).iterdir())

    execute(channel, db_session=db_session)
    second = _manifest(tmp_path)

    assert second.snapshot_id == first.snapshot_id
    assert sorted(path.name for path in (tmp_path / SNAPSHOTS_DIR).iterdir()) == first_dirs


def test_two_destinations_with_the_same_records_hash_the_same(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(tmp_path))

    execute(channel, db_session=db_session)
    first = _manifest(tmp_path)

    other = tmp_path / "other"
    channel.config = DatasetConfig.model_validate(_config(other)).model_dump(mode="json", exclude_none=True)
    db_session.commit()
    execute(channel, db_session=db_session)
    second = _manifest(other)

    assert second.snapshot_id == first.snapshot_id
    assert [(artifact.path, artifact.sha256) for artifact in second.artifacts] == [
        (artifact.path, artifact.sha256) for artifact in first.artifacts
    ]


# ==========================================
# REMOVALS
# ==========================================


def test_a_record_that_leaves_the_set_is_listed_in_removals(db_session: Session, tmp_path: Path) -> None:
    a_channel(db_session, DATASET_CODE)
    a_node(db_session, "fundo", title="Fundo A")
    a_node(db_session, "fica", parent_id="fundo", title="Fica")
    sai = a_node(db_session, "sai", parent_id="fundo", title="Sai")
    a_scope(db_session, "fundo", channel_code=DATASET_CODE)
    db_session.commit()
    channel = _channel(db_session, _config(tmp_path))
    execute(channel, db_session=db_session)
    first = _manifest(tmp_path)

    sai.review_status = ArchiveReviewStatus.PENDING_AI
    db_session.commit()
    execute(channel, db_session=db_session)
    second = _manifest(tmp_path)

    assert second.previous_snapshot_id == first.snapshot_id
    assert second.removals == ["sai"]
    assert second.record_count == 2
    lines = (_snapshot_dir(tmp_path) / DATA_FILES["ndjson"]).read_text(encoding="utf-8")
    assert '"description_id":"sai"' not in lines


# ==========================================
# REFUSALS
# ==========================================


def test_a_run_without_a_destination_refuses(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(None))

    with pytest.raises(InvalidDiffusionConfigError, match="não tem destino"):
        execute(channel, db_session=db_session)


def test_a_destination_that_is_a_file_refuses(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    file_path = tmp_path / "arquivo"
    file_path.write_text("x", encoding="utf-8")
    channel = _channel(db_session, _config(file_path))

    with pytest.raises(InvalidDiffusionConfigError, match="arquivo"):
        execute(channel, db_session=db_session)


def test_a_run_without_an_institution_refuses(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    config = _config(tmp_path)
    config.pop("institution_name")
    config.pop("contact_email")
    channel = _channel(db_session, config)

    with pytest.raises(InvalidDiffusionConfigError, match="instituição"):
        execute(channel, db_session=db_session)


def test_the_institution_falls_back_to_the_public_site(db_session: Session, tmp_path: Path) -> None:
    site = a_channel(db_session, "public_site")
    site.config = PublicSiteConfig.model_validate(
        {
            "site_title": "Site",
            "institution_name": "Instituição do site",
            "contact_email": "site@example.org",
            "public_base_url": "https://example.org",
        }
    ).model_dump(mode="json", exclude_none=True)
    _publish_a_branch(db_session)
    config = _config(tmp_path)
    config.pop("institution_name")
    config.pop("contact_email")
    channel = _channel(db_session, config)

    execute(channel, db_session=db_session)

    manifest = _manifest(tmp_path)
    assert manifest.institution.name == "Instituição do site"
    assert manifest.institution.contact_email == "site@example.org"
    assert str(manifest.api_url) == "https://example.org/api/v1/public/documents"
    assert str(manifest.openapi_url) == "https://example.org/schema"


def test_a_corrupt_pointer_refuses(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(tmp_path))
    (tmp_path / CURRENT_POINTER).write_text("../../etc", encoding="utf-8")

    with pytest.raises(InvalidDiffusionConfigError, match="snapshot válido"):
        execute(channel, db_session=db_session)


# ==========================================
# RETENTION AND PREVIEW
# ==========================================


def test_retention_keeps_only_the_current_snapshot_when_it_is_one(db_session: Session, tmp_path: Path) -> None:
    a_channel(db_session, DATASET_CODE)
    a_node(db_session, "fundo", title="Fundo A")
    a_node(db_session, "a", parent_id="fundo", title="A")
    b = a_node(db_session, "b", parent_id="fundo", title="B")
    a_scope(db_session, "fundo", channel_code=DATASET_CODE)
    db_session.commit()
    channel = _channel(db_session, _config(tmp_path, retention=1))

    execute(channel, db_session=db_session)
    first = _manifest(tmp_path)

    b.review_status = ArchiveReviewStatus.PENDING_AI
    db_session.commit()
    execute(channel, db_session=db_session)

    remaining = [path.name for path in (tmp_path / SNAPSHOTS_DIR).iterdir()]
    assert remaining == [_manifest(tmp_path).snapshot_id]
    assert first.snapshot_id not in remaining


def test_the_preview_reports_what_the_run_would_write(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(tmp_path))

    result = preview(channel, db_session=db_session)

    assert isinstance(result, DatasetPreview)
    assert result.ready is True
    assert result.record_count == 3
    assert len(result.artifacts) == 3
    assert result.removals == ()
    assert result.unchanged is False
    assert not (tmp_path / CURRENT_POINTER).exists()


def test_the_preview_reports_a_missing_destination_instead_of_raising(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(None))

    result = preview(channel, db_session=db_session)

    assert result.ready is False
    assert result.reason is not None and "destino" in result.reason


def test_the_preview_of_an_unchanged_set_says_so(db_session: Session, tmp_path: Path) -> None:
    _publish_a_branch(db_session)
    channel = _channel(db_session, _config(tmp_path))
    execute(channel, db_session=db_session)

    result = preview(channel, db_session=db_session)

    assert result.ready is True
    assert result.unchanged is True
    assert result.previous_snapshot_id == result.snapshot_id
