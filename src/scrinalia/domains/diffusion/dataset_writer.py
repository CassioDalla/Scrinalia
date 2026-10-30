"""The open dataset's adapter: writes the snapshot, its manifest and its field map (ADR 0024).

One run is one snapshot of the ``dataset`` channel. The adapter reads the covered set through the one
coverage definition, renders the public projection into the configured formats, and publishes the
result atomically under the destination:

    <destination>/current                     the id of the snapshot a reader should use
    <destination>/snapshots/<snapshot_id>/     the package itself
        documents.ndjson | documents.json | documents.csv
        manifest.json
        field-map.json
        LICENSE.txt
        README.md

**The snapshot is a pure function of the covered set plus the configuration**, except for the
manifest's ``generated_at``. The record files carry no timestamp, the records are ordered by
``description_id``, and the JSON is canonical, so two runs over the same set produce the same bytes and
the same checksums. ``snapshot_id`` is the SHA-256 of the canonical records and not of the files, so it
does not depend on which formats were enabled.

**A rerun with the same content writes nothing.** The current snapshot's id is compared first; when it
matches, the run ends successfully without a new directory, and the UI can report "unchanged".

**Removals are the difference between the previous manifest's ids and the current ones.** The dataset
keeps no tombstone: the published coverage is the truth, and a consumer that misses a run compares
snapshots. The previous snapshot's ids are read from its data file (NDJSON, JSON or CSV), never from a
second registry.

The destination is local on purpose (ADR 0024): no object storage is required, and the operator can
serve the directory with any web server. The download route is 214c.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import uuid4

from pydantic import HttpUrl, ValidationError
from sqlalchemy.orm import Session

from scrinalia.core.attribution import ATTRIBUTION
from scrinalia.core.i18n import t
from scrinalia.core.logger import logger
from scrinalia.core.version import application_version
from scrinalia.domains.archive.repository.document_repo import DocumentRepository
from scrinalia.domains.archive.schemas.document_schema import DocumentSummary
from scrinalia.domains.archive.schemas.public_projection import PublicDocumentSummary
from scrinalia.domains.archive.workers.cancellation import RunControl
from scrinalia.domains.diffusion.dataset_contract import (
    DATASET_FIELDS,
    DATASET_SCHEMA_VERSION,
    DatasetArtifact,
    DatasetInstitution,
    DatasetLicense,
    DatasetManifest,
    DatasetSoftware,
    field_map_document,
)
from scrinalia.domains.diffusion.diffusion_registry import (
    DATASET_CODE,
    PUBLIC_SITE_CODE,
    DatasetConfig,
    PublicSiteConfig,
)
from scrinalia.domains.diffusion.exceptions import InvalidDiffusionConfigError
from scrinalia.domains.diffusion.models import DiffusionChannel
from scrinalia.domains.diffusion.repository import DiffusionChannelRepository

#: The name of the pointer file and of the snapshot directory inside the destination.
CURRENT_POINTER = "current"
SNAPSHOTS_DIR = "snapshots"

#: One description per page; the cancellation is checked at these boundaries.
PAGE_SIZE = 500

#: The canonical NDJSON the checksum covers, before it is renamed to the published file.
_CANONICAL_RECORDS = ".records.ndjson"

#: The file each format writes, in the order the manifest lists them.
DATA_FILES: dict[Literal["json", "ndjson", "csv"], str] = {
    "json": "documents.json",
    "ndjson": "documents.ndjson",
    "csv": "documents.csv",
}

#: A snapshot id is a SHA-256 hex digest. The pointer is read from disk, so it is validated before it
#: becomes a path: a corrupt file must not become ``../..``.
_SNAPSHOT_ID = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class DatasetPreview:
    """
    What a run would write, without writing it.

    It is computed by rendering the whole package into a temporary directory (system temp, never the
    destination), so the sizes are exact and the removals are the ones the run would record. ``ready``
    is false when the configuration still has a hole — no destination, an incomplete license, no
    institution — and ``reason`` is the sentence the operator can act on.
    """

    record_count: int
    artifacts: tuple[DatasetArtifact, ...]
    removals: tuple[str, ...]
    previous_snapshot_id: str | None
    snapshot_id: str
    unchanged: bool
    destination: str | None
    ready: bool
    reason: str | None


@dataclass(frozen=True)
class _Rendered:
    """The data files written into one directory, with the identity of what they contain."""

    artifacts: tuple[DatasetArtifact, ...]
    record_count: int
    snapshot_id: str
    ids: frozenset[str]


@dataclass(frozen=True)
class _Previous:
    """The current snapshot before this run: its manifest and the ids it carried."""

    manifest: DatasetManifest
    ids: frozenset[str]


# =========================================================================
# THE RUN
# =========================================================================


def execute(channel: DiffusionChannel, *, db_session: Session, run_control: RunControl | None = None) -> None:
    """
    Writes one snapshot of the ``dataset`` channel.

    A channel that is not the dataset is a programming error: the registry maps the module to this
    channel, and the worker already refused every other code. The refusals the operator can fix (no
    destination, an incomplete license, no institution) are ``InvalidDiffusionConfigError`` with a
    sentence; the ledger records the cause and the fingerprint groups it.
    """
    if channel.code != DATASET_CODE:
        raise InvalidDiffusionConfigError(
            t("O exportador do conjunto de dados recebeu o canal '{code}'.", code=channel.code)
        )

    config = _config(channel)
    destination = _destination(config)
    license_ = _license(config)
    institution = _institution(db_session, config)
    previous = _current_snapshot(destination)

    destination.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=destination, prefix=".tmp-"))
    try:
        rendered = _render(tmp, config, db_session, run_control)
        if previous is not None and previous.manifest.snapshot_id == rendered.snapshot_id:
            logger.info(f"📦 Dataset inalterado em {destination} ({rendered.record_count} registros).")
            return

        manifest = _manifest(rendered, config, license_, institution, db_session, previous)
        _write_manifest(tmp, manifest)
        _write_field_map(tmp)
        _write_license(tmp, license_)
        _write_readme(tmp, config, manifest)
        _publish(tmp, destination, rendered.snapshot_id, config.retention)
        logger.info(
            f"📦 Dataset publicado em {destination} ({rendered.record_count} registros, "
            f"snapshot {rendered.snapshot_id[:12]})."
        )
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def preview(channel: DiffusionChannel, *, db_session: Session) -> DatasetPreview:
    """
    Renders the package to a temporary directory and reports what the run would write.

    It writes nothing to the destination and creates no ledger row: the run is a plan, the execute is
    the write. The cancellation is not consulted — a preview is bounded by the collection, not by an
    operator stopping a run that does not exist.
    """
    config = _config(channel)
    reasons: list[str] = []
    destination_reason = _destination_reason(config)
    if destination_reason is not None:
        reasons.append(destination_reason)
    try:
        _license(config)
    except InvalidDiffusionConfigError as exc:
        reasons.append(str(exc))
    try:
        _institution(db_session, config)
    except InvalidDiffusionConfigError as exc:
        reasons.append(str(exc))

    destination = Path(config.destination_path) if config.destination_path else None
    previous = _current_snapshot(destination) if destination is not None and destination.exists() else None
    with tempfile.TemporaryDirectory(prefix="dataset-preview-") as directory:
        rendered = _render(Path(directory), config, db_session, run_control=None)

    removals = tuple(sorted(previous.ids - rendered.ids)) if previous is not None else ()
    unchanged = previous is not None and previous.manifest.snapshot_id == rendered.snapshot_id
    return DatasetPreview(
        record_count=rendered.record_count,
        artifacts=rendered.artifacts,
        removals=removals,
        previous_snapshot_id=previous.manifest.snapshot_id if previous is not None else None,
        snapshot_id=rendered.snapshot_id,
        unchanged=unchanged,
        destination=str(destination) if destination is not None else None,
        ready=not reasons,
        reason="; ".join(reasons) if reasons else None,
    )


# =========================================================================
# THE CONFIGURATION AND THE FALLBACKS
# =========================================================================


def _config(channel: DiffusionChannel) -> DatasetConfig:
    """The channel's JSONB as the model the registry declares; a bad row is a sentence, not a 500."""
    try:
        return DatasetConfig.model_validate(dict(channel.config or {}))
    except ValidationError as exc:
        raise InvalidDiffusionConfigError(t("Configuração inválida do canal 'dataset': {exc}", exc=exc)) from exc


def _destination(config: DatasetConfig) -> Path:
    """The absolute destination, or the sentence that says why the run cannot start."""
    if config.destination_path is None:
        raise InvalidDiffusionConfigError(
            t("O canal 'dataset' não tem destino. Informe o diretório onde o snapshot será escrito.")
        )
    path = Path(config.destination_path)
    if path.exists() and not path.is_dir():
        raise InvalidDiffusionConfigError(t("O destino '{path}' é um arquivo, não um diretório.", path=path))
    return path


def _destination_reason(config: DatasetConfig) -> str | None:
    """Why the configured destination is not usable yet, or ``None`` when it is."""
    if config.destination_path is None:
        return t("O canal 'dataset' não tem destino. Informe o diretório onde o snapshot será escrito.")
    path = Path(config.destination_path)
    if path.exists() and not path.is_dir():
        return t("O destino '{path}' é um arquivo, não um diretório.", path=path)
    if not path.exists() and not path.parent.exists():
        return t("O diretório pai do destino '{path}' não existe.", path=path.parent)
    return None


def _license(config: DatasetConfig) -> DatasetLicense:
    """The license the manifest declares, with the rules of the contract applied."""
    try:
        return config.as_license()
    except ValidationError as exc:
        raise InvalidDiffusionConfigError(t("A licença de dados do conjunto está incompleta: {exc}", exc=exc)) from exc


def _institution(db: Session, config: DatasetConfig) -> DatasetInstitution:
    """
    Who publishes the package: the channel's own fields, or the public site's identity.

    The fallback is the issue's "the contact/institution from the public_site identity if it exists, or
    its own config". Both channels are rows in the same table; reading the other one is a read, not a
    second decision.
    """
    name = config.institution_name
    contact = config.contact_email
    if not name or not contact:
        site = _public_site_config(db)
        if site is not None:
            name = name or site.institution_name
            contact = contact or site.contact_email
    if not name:
        raise InvalidDiffusionConfigError(
            t("Informe a instituição responsável pelo conjunto ou configure a instituição do site público.")
        )
    return DatasetInstitution(name=name, contact_email=contact)


def _public_site_config(db: Session) -> PublicSiteConfig | None:
    """The public site's identity, when the channel exists and its config is complete enough."""
    channel = DiffusionChannelRepository(db).get(PUBLIC_SITE_CODE)
    if channel is None:
        return None
    try:
        return PublicSiteConfig.model_validate(dict(channel.config or {}))
    except ValidationError:
        return None


def _api_urls(db: Session, config: DatasetConfig) -> tuple[str | None, str | None]:
    """The live API and its OpenAPI document, when the installation publishes an address for them."""
    base = config.api_base_url
    if base is None:
        site = _public_site_config(db)
        if site is not None:
            base = site.public_base_url
    if base is None:
        return None, None
    root = str(base).rstrip("/")
    return f"{root}/api/v1/public/documents", f"{root}/schema"


# =========================================================================
# THE RENDER
# =========================================================================


def _render(
    directory: Path,
    config: DatasetConfig,
    db: Session,
    run_control: RunControl | None,
) -> _Rendered:
    """
    Writes the enabled formats into ``directory`` and computes the snapshot's identity.

    The canonical NDJSON is written first, in one explicit ``with``: it is the bytes the checksum
    covers and the source the JSON and CSV are derived from. Deriving instead of writing three files
    from one in-memory loop keeps every handle in a ``with`` — ``ExitStack`` is correct but invisible
    to CodeQL's unclosed-file analysis, and a suppression would hide the next real one.
    """
    formats = config.formats
    count = 0
    ids: set[str] = set()
    digest = hashlib.sha256()
    canonical = directory / _CANONICAL_RECORDS

    with canonical.open("w", encoding="utf-8", newline="\n") as records:
        for record in _iter_records(db, run_control):
            line = _canonical(record)
            records.write(line)
            records.write("\n")
            digest.update(line.encode("utf-8"))
            digest.update(b"\n")
            ids.add(str(record["description_id"]))
            count += 1

    if "json" in formats:
        _write_json(directory / DATA_FILES["json"], canonical, count)
    if "csv" in formats:
        _write_csv(directory / DATA_FILES["csv"], canonical)
    if "ndjson" in formats:
        os.replace(canonical, directory / DATA_FILES["ndjson"])
    else:
        canonical.unlink(missing_ok=True)

    artifacts = tuple(_artifact(name, directory / DATA_FILES[name], count) for name in formats)
    return _Rendered(artifacts=artifacts, record_count=count, snapshot_id=digest.hexdigest(), ids=frozenset(ids))


def _write_json(target: Path, source: Path, count: int) -> None:
    """The envelope around the canonical records, streamed so a large set is never held in memory."""
    with source.open(encoding="utf-8") as records, target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f'{{"schema_version":"{DATASET_SCHEMA_VERSION}","items":[')
        first = True
        for line in records:
            if not line.strip():
                continue
            if not first:
                handle.write(",")
            handle.write(line.rstrip("\n"))
            first = False
        handle.write(f'],"record_count":{count}}}')


def _write_csv(target: Path, source: Path) -> None:
    """The flat projection, one row per record, a list or an object as JSON in its cell."""
    with source.open(encoding="utf-8") as records, target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([field.name for field in DATASET_FIELDS])
        for line in records:
            if not line.strip():
                continue
            record = json.loads(line)
            writer.writerow([_csv_cell(record.get(field.name)) for field in DATASET_FIELDS])


def _iter_records(db: Session, run_control: RunControl | None) -> Iterator[dict[str, Any]]:
    """
    The covered records, page by page, in ``description_id`` order.

    The projection is ``PublicDocumentSummary.from_summary`` and nothing else: a field is exported
    because it is in the allowlist, and the field map classifies the same model.
    """
    repo = DocumentRepository(db)
    after: str | None = None
    while True:
        if run_control is not None:
            run_control.checkpoint()
        page: list[DocumentSummary] = repo.list_channel_documents(DATASET_CODE, after=after, limit=PAGE_SIZE)
        if not page:
            return
        for summary in page:
            yield PublicDocumentSummary.from_summary(summary).model_dump(mode="json")
        after = page[-1].description_id


def _canonical(record: dict[str, Any]) -> str:
    """The one serialization the checksums and the NDJSON file share."""
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _csv_cell(value: Any) -> str:
    """A cell of the flat projection; a list or an object is JSON, never an ambiguous separator."""
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _artifact(format: Literal["json", "ndjson", "csv"], path: Path, records: int) -> DatasetArtifact:
    """One written file, with the hash a consumer verifies before ingesting it."""
    data = path.read_bytes()
    return DatasetArtifact(
        format=format,
        path=path.name,
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        records=records,
    )


# =========================================================================
# THE MANIFEST AND THE SATELLITES
# =========================================================================


def _manifest(
    rendered: _Rendered,
    config: DatasetConfig,
    license_: DatasetLicense,
    institution: DatasetInstitution,
    db: Session,
    previous: _Previous | None,
) -> DatasetManifest:
    """The package's own description, built after the data so the hashes are the bytes on disk."""
    api_url, openapi_url = _api_urls(db, config)
    return DatasetManifest(
        schema_version=DATASET_SCHEMA_VERSION,
        snapshot_id=rendered.snapshot_id,
        previous_snapshot_id=previous.manifest.snapshot_id if previous is not None else None,
        generated_at=datetime.now(UTC),
        record_count=rendered.record_count,
        artifacts=list(rendered.artifacts),
        removals=sorted(previous.ids - rendered.ids) if previous is not None else [],
        license=license_,
        institution=institution,
        software=DatasetSoftware(
            name=ATTRIBUTION.name,
            version=application_version(),
            license=ATTRIBUTION.license,
            license_url=HttpUrl(ATTRIBUTION.license_url),
            source_url=HttpUrl(ATTRIBUTION.source_url),
        ),
        api_url=HttpUrl(api_url) if api_url is not None else None,
        openapi_url=HttpUrl(openapi_url) if openapi_url is not None else None,
    )


def _write_manifest(directory: Path, manifest: DatasetManifest) -> None:
    """Writes the manifest as deterministic JSON; ``generated_at`` is the only time-dependent value."""
    payload = manifest.model_dump(mode="json")
    (directory / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_field_map(directory: Path) -> None:
    """Writes the published crosswalk from the same function the committed artifact comes from."""
    (directory / "field-map.json").write_text(
        json.dumps(field_map_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_license(directory: Path, license_: DatasetLicense) -> None:
    """The data license, with the terms a consumer must carry; the software license is separate."""
    lines = [f"Data license: {license_.name} ({license_.id})"]
    if license_.url is not None:
        lines.append(f"URL: {license_.url}")
    if license_.attribution is not None:
        lines.append(f"Attribution: {license_.attribution}")
    lines.append("")
    lines.append(
        f"The software that generated this package is {ATTRIBUTION.name}, licensed under "
        f"{ATTRIBUTION.license} ({ATTRIBUTION.license_url}); its source is {ATTRIBUTION.source_url}."
    )
    (directory / "LICENSE.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_readme(directory: Path, config: DatasetConfig, manifest: DatasetManifest) -> None:
    """The human entry point of the package: what it is, how to read it and where the live API is."""
    lines = [
        f"# {config.dataset_title}",
        "",
        config.dataset_description or "",
        "",
        f"This is a snapshot of the descriptions published on the `dataset` channel by "
        f"{manifest.institution.name}, generated by {ATTRIBUTION.name} {manifest.software.version} "
        f"on {manifest.generated_at.isoformat()}.",
        "",
        f"- Records: {manifest.record_count}",
        f"- Schema version: {manifest.schema_version}",
        f"- Snapshot: `{manifest.snapshot_id}`",
        f"- Data license: {manifest.license.name}"
        + (f" — {manifest.license.attribution}" if manifest.license.attribution else ""),
        f"- Field map: `{manifest.field_map}`",
        "",
        "## Files",
        "",
        *[
            f"- `{artifact.path}` — {artifact.records} records, {artifact.bytes} bytes"
            for artifact in manifest.artifacts
        ],
        "",
        "The record shape and the ISAD(G) crosswalk are in `field-map.json`. The manifest lists every",
        "file with its SHA-256; verify them before ingesting. A consumer that misses a run compares two",
        "snapshots: `removals` lists the ids that left since the previous one, and the dataset keeps no",
        "tombstone of its own.",
        "",
    ]
    if manifest.api_url is not None:
        lines.extend(
            [
                "## Live API",
                "",
                f"The same channel is readable live at {manifest.api_url}; the OpenAPI document is at "
                f"{manifest.openapi_url}.",
                "",
            ]
        )
    lines.extend(
        [
            "## Software",
            "",
            f"{ATTRIBUTION.name} {manifest.software.version} — {ATTRIBUTION.license} — {ATTRIBUTION.source_url}",
            "",
        ]
    )
    (directory / "README.md").write_text("\n".join(lines), encoding="utf-8")


# =========================================================================
# THE PUBLICATION
# =========================================================================


def _current_snapshot(destination: Path) -> _Previous | None:
    """
    The snapshot the ``current`` pointer names, with its ids, or ``None`` on the first run.

    The pointer is read from disk and validated before it becomes a path: a truncated or edited file
    must be a sentence, not a directory traversal.
    """
    pointer = destination / CURRENT_POINTER
    if not pointer.is_file():
        return None
    snapshot_id = pointer.read_text(encoding="utf-8").strip()
    if not _SNAPSHOT_ID.fullmatch(snapshot_id):
        raise InvalidDiffusionConfigError(
            t("O ponteiro '{pointer}' do destino não aponta para um snapshot válido.", pointer=pointer)
        )
    snapshot = destination / SNAPSHOTS_DIR / snapshot_id
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.is_file():
        raise InvalidDiffusionConfigError(
            t("O manifesto do snapshot '{id}' não existe em '{path}'.", id=snapshot_id, path=snapshot)
        )
    try:
        manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise InvalidDiffusionConfigError(
            t("O manifesto do snapshot '{id}' não pôde ser lido: {exc}", id=snapshot_id, exc=exc)
        ) from exc
    return _Previous(manifest=manifest, ids=_read_ids(snapshot, manifest))


def _read_ids(snapshot: Path, manifest: DatasetManifest) -> frozenset[str]:
    """
    The description ids a previous snapshot carried, from its first readable data file.

    NDJSON, then JSON, then CSV: the writer always produces at least one of them, and the preference
    keeps the read cheap for the format a custom site consumes.
    """
    by_format = {artifact.format: artifact for artifact in manifest.artifacts}
    for format in ("ndjson", "json", "csv"):
        artifact = by_format.get(format)
        if artifact is None:
            continue
        name = PurePosixPath(artifact.path).name
        if name != artifact.path:
            raise InvalidDiffusionConfigError(
                t("O manifesto lista um caminho inválido para o snapshot: '{path}'.", path=artifact.path)
            )
        path = snapshot / name
        if not path.is_file():
            continue
        if format == "ndjson":
            return frozenset(_ids_from_ndjson(path))
        if format == "json":
            return frozenset(_ids_from_json(path))
        return frozenset(_ids_from_csv(path))
    raise InvalidDiffusionConfigError(
        t(
            "O snapshot '{id}' não tem nenhum arquivo de dados que o próximo run possa comparar.",
            id=manifest.snapshot_id,
        )
    )


def _ids_from_ndjson(path: Path) -> Iterator[str]:
    """One JSON object per line, the canonical record."""
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield str(json.loads(line)["description_id"])
            except (json.JSONDecodeError, KeyError) as exc:
                raise InvalidDiffusionConfigError(
                    t("A linha {number} de '{path}' não é um registro válido.", number=number, path=path)
                ) from exc


def _ids_from_json(path: Path) -> Iterator[str]:
    """The envelope's ``items``, the format a small custom site reads in one request."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        return iter([str(item["description_id"]) for item in document["items"]])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise InvalidDiffusionConfigError(t("'{path}' não é um documents.json válido.", path=path)) from exc


def _ids_from_csv(path: Path) -> Iterator[str]:
    """The flat projection; the first column is the id, whatever the others are."""
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                yield str(row["description_id"])
    except (KeyError, csv.Error) as exc:
        raise InvalidDiffusionConfigError(t("'{path}' não é um documents.csv válido.", path=path)) from exc


def _publish(tmp: Path, destination: Path, snapshot_id: str, retention: int) -> None:
    """
    Moves the rendered directory into place and flips the pointer.

    The rename is the atomic step: a reader sees the previous snapshot or the new one, never a
    half-written directory. A rerun whose id already exists is not deleted here — the caller returned
    "unchanged" before reaching this point — so an existing directory is an old snapshot whose content
    returned, and replacing it keeps the transition metadata (``previous_snapshot_id``, ``removals``)
    of this run instead of the stale one.
    """
    snapshots = destination / SNAPSHOTS_DIR
    snapshots.mkdir(parents=True, exist_ok=True)
    final = snapshots / snapshot_id
    if final.exists():
        shutil.rmtree(final)
    os.replace(tmp, final)
    _write_pointer(destination, snapshot_id)
    _prune(snapshots, retention, current=snapshot_id)


def _write_pointer(destination: Path, snapshot_id: str) -> None:
    """Replaces the ``current`` file atomically: a reader never sees a truncated id."""
    temporary = destination / f".current-{uuid4().hex}"
    temporary.write_text(snapshot_id + "\n", encoding="utf-8")
    os.replace(temporary, destination / CURRENT_POINTER)


def _prune(snapshots: Path, retention: int, *, current: str) -> None:
    """Keeps the newest snapshots and the current one, and removes the rest."""
    snapshot_dirs = [path for path in snapshots.iterdir() if path.is_dir() and _SNAPSHOT_ID.fullmatch(path.name)]
    if len(snapshot_dirs) <= retention:
        return
    keep = {path.name for path in sorted(snapshot_dirs, key=_generated_at, reverse=True)[:retention]}
    keep.add(current)
    for path in snapshot_dirs:
        if path.name not in keep:
            shutil.rmtree(path, ignore_errors=True)


def _generated_at(snapshot: Path) -> str:
    """The manifest's timestamp, for an order that survives a clock change; '' when unreadable."""
    try:
        return str(json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))["generated_at"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return ""
