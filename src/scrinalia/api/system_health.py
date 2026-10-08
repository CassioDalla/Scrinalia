"""Infrastructure probes behind ``GET /system/health``.

They live in the composition layer because they cross boundaries on purpose: the database counts
read the archive models, the Ollama probe reads the engine presets, and the storage probe reads the
core settings. Putting them in ``core`` would make the innermost layer import the domains.

Each probe is isolated and time-boxed, and none of them raises: the operations screen has to show
*which* piece is down, so a database that is offline must not turn the whole endpoint into a 500.
No secret value ever leaves here — the process probe reports presence, never content.
"""

from __future__ import annotations

from datetime import UTC, datetime

import requests
from sqlalchemy import func, select, text

from scrinalia.core.config import DEFAULT_OLLAMA_HOST, settings
from scrinalia.core.database import create_session
from scrinalia.domains.archive.models import ArchiveDocument, ArchiveEntity, ArchiveTag
from scrinalia.domains.archive.schemas.system_schema import (
    DatabaseHealthDTO,
    OllamaHealthDTO,
    ProcessHealthDTO,
    StorageHealthDTO,
    SystemHealthResponse,
)
from scrinalia.domains.archive.workers.catalogue import axis_registry

#: Short on purpose: the panel is a human waiting on a screen, not a monitoring agent.
NETWORK_TIMEOUT_SECONDS = 2.0

#: Cap on the error text a probe reports, so a driver's stack does not become the screen.
DETAIL_LIMIT = 300


def _detail(exc: BaseException) -> str:
    return str(exc)[:DETAIL_LIMIT]


def probe_database() -> DatabaseHealthDTO:
    """Liveness plus the denominators the queues are read against."""
    try:
        with create_session() as db:
            db.execute(text("SELECT 1"))
            return DatabaseHealthDTO(
                ok=True,
                documents=int(db.scalar(select(func.count()).select_from(ArchiveDocument)) or 0),
                tags=int(db.scalar(select(func.count()).select_from(ArchiveTag)) or 0),
                entities=int(db.scalar(select(func.count()).select_from(ArchiveEntity)) or 0),
                staging_records=int(db.scalar(text("SELECT count(*) FROM staging_documents")) or 0),
            )
    except Exception as exc:
        return DatabaseHealthDTO(ok=False, detail=_detail(exc))


def required_ollama_models() -> list[str]:
    """
    Every model the presets name, across the two axes that talk to Ollama.

    The title reviewer is included even though its worker is opt-in: a missing model is exactly the
    silent failure the diagnosis exists to surface before a run discovers it.
    """
    models: set[str] = set()
    for axis in ("LLMs", "title_quality"):
        for preset in axis_registry(axis).PRESETS.values():
            model = preset.get("model")
            if model:
                models.add(str(model))
    return sorted(models)


def probe_ollama() -> OllamaHealthDTO:
    """Lists the models the server actually has, and what the presets demand of it."""
    host = settings.OLLAMA_HOST_URL or DEFAULT_OLLAMA_HOST
    host_source = "OLLAMA_HOST_URL" if settings.OLLAMA_HOST_URL else "default"
    required = required_ollama_models()

    try:
        response = requests.get(f"{host}/api/tags", timeout=NETWORK_TIMEOUT_SECONDS)
        response.raise_for_status()
        installed = sorted(str(model.get("name")) for model in response.json().get("models", []))
    except Exception as exc:
        return OllamaHealthDTO(
            ok=False, host=host, host_source=host_source, detail=_detail(exc), required_models=required
        )

    return OllamaHealthDTO(
        ok=True,
        host=host,
        host_source=host_source,
        installed_models=installed,
        required_models=required,
        missing_models=[model for model in required if model not in installed],
    )


def probe_storage() -> StorageHealthDTO:
    """Whether the bucket the thumbnails go to is reachable."""
    endpoint = settings.S3_ENDPOINT_URL
    bucket = settings.S3_BUCKET_NAME

    if not endpoint or not bucket or settings.S3_ACCESS_KEY is None or settings.S3_SECRET_KEY is None:
        return StorageHealthDTO(
            configured=False,
            ok=False,
            endpoint=endpoint,
            bucket=bucket,
            detail="S3 não configurado: faltam endpoint, bucket ou credenciais.",
        )

    try:
        # Imported here: boto3 costs a few hundred milliseconds and only this probe needs it.
        import boto3
        from botocore.client import Config

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.S3_ACCESS_KEY.get_secret_value(),
            aws_secret_access_key=settings.S3_SECRET_KEY.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                connect_timeout=NETWORK_TIMEOUT_SECONDS,
                read_timeout=NETWORK_TIMEOUT_SECONDS,
                retries={"max_attempts": 0},
            ),
        )
        client.head_bucket(Bucket=bucket)
        return StorageHealthDTO(configured=True, ok=True, endpoint=endpoint, bucket=bucket)
    except Exception as exc:
        return StorageHealthDTO(configured=True, ok=False, endpoint=endpoint, bucket=bucket, detail=_detail(exc))


def probe_process() -> ProcessHealthDTO:
    """The effective environment, with secrets reduced to a boolean."""
    return ProcessHealthDTO(
        log_level=settings.LOG_LEVEL,
        debug=settings.DEBUG,
        log_dir=settings.LOG_DIR,
        database=f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
        ollama_host_url=settings.OLLAMA_HOST_URL,
        s3_endpoint_url=settings.S3_ENDPOINT_URL,
        s3_bucket_name=settings.S3_BUCKET_NAME,
        public_scrape_configured=bool(settings.PUBLIC_SCRAPE_URL),
        secrets_present={
            "DB_PASS": bool(settings.DB_PASS.get_secret_value()),
            "S3_ACCESS_KEY": settings.S3_ACCESS_KEY is not None,
            "S3_SECRET_KEY": settings.S3_SECRET_KEY is not None,
        },
    )


def probe_infrastructure() -> SystemHealthResponse:
    """Runs every probe; each one answers on its own."""
    return SystemHealthResponse(
        generated_at=datetime.now(UTC),
        database=probe_database(),
        ollama=probe_ollama(),
        storage=probe_storage(),
        process=probe_process(),
    )
