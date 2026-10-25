from io import BytesIO
from urllib.parse import urlsplit

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from pydantic import SecretStr

from scrinalia.core.config import settings
from scrinalia.core.exceptions import DomainException
from scrinalia.core.logger import logger

#: The error codes an S3-compatible endpoint answers when the bucket is not there. AWS and MinIO
#: answer ``NoSuchBucket``/``NotFound``; SeaweedFS answers a bare ``404`` on ``HeadBucket``, and
#: botocore leaves that string as the code when the endpoint sends no error body. The HTTP status is
#: checked beside the code because some endpoints send neither a code nor a body.
_MISSING_BUCKET_CODES = frozenset({"404", "NoSuchBucket", "NotFound"})

#: The codes that mean the key is not there, which is a **read** failure and not a broken endpoint.
#: ``NoSuchBucket`` belongs here too: from the reader's side a removed bucket and a removed object
#: are the same answer — there are no bytes to serve — and the API turns both into a 404 while the
#: log keeps the distinction.
_MISSING_OBJECT_CODES = frozenset({"404", "NoSuchBucket", "NoSuchKey", "NotFound"})

#: The codes that mean somebody else created the bucket between our ``HeadBucket`` and our
#: ``CreateBucket``. Both are success here: the bucket exists and we can write into it.
_ALREADY_EXISTS_CODES = frozenset({"BucketAlreadyExists", "BucketAlreadyOwnedByYou"})


class ObjectStorageError(DomainException):
    """
    The object storage cannot take the upload: unconfigured, unreachable, or without its bucket.

    It is a ``DomainException`` for the same reason ``EngineExecutionError`` is one: the sentence is
    Portuguese and operator-facing, and it ends up in the run ledger's ``error`` column, which the
    panel shows. It is never raised inside the per-document loop — the worker checks the bucket once,
    before it touches the queue, so a missing bucket fails the run instead of stamping every document
    with a failure the endpoint reported as ``AccessDenied``.
    """


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _http_status(exc: ClientError) -> int | None:
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return int(status) if status is not None else None


def is_missing_bucket_error(exc: ClientError) -> bool:
    """Whether the endpoint answered "that bucket does not exist" (and not "you may not touch it")."""
    return _error_code(exc) in _MISSING_BUCKET_CODES or _http_status(exc) == 404


def is_already_exists_error(exc: ClientError) -> bool:
    """Whether the endpoint answered "the bucket is already there", which is success for us."""
    return _error_code(exc) in _ALREADY_EXISTS_CODES or _http_status(exc) == 409


def is_missing_object_error(exc: ClientError) -> bool:
    """Whether the endpoint answered "that key is not there", which is a read that found nothing."""
    return _error_code(exc) in _MISSING_OBJECT_CODES or _http_status(exc) == 404


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """
    Splits the ``s3://bucket/key`` the thumbnail worker writes into the bucket and the key.

    The bucket comes from the URI and **not** from the settings on purpose: a row written before the
    installation moved to another bucket still names the object it stored, and refusing it because
    the current configuration names a different one would turn a working archive into a broken one.
    A URI that is not a complete ``s3://`` reference raises ``ValueError`` — that is a malformed row,
    not a missing object, and the caller decides how to report it.
    """
    parsed = urlsplit(uri)
    key = parsed.path.lstrip("/")
    if parsed.scheme != "s3" or not parsed.netloc or not key:
        raise ValueError(f"not a complete s3://bucket/key URI: {uri!r}")
    return parsed.netloc, key


def _reveal(secret: SecretStr | None) -> str | None:
    """Unwraps a SecretStr for the S3 client, which expects plain credentials."""
    return secret.get_secret_value() if secret is not None else None


class S3Storage:
    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET_NAME

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=_reveal(settings.S3_ACCESS_KEY),
            aws_secret_access_key=_reveal(settings.S3_SECRET_KEY),
            config=Config(signature_version="s3v4"),
        )
        #: Set once the bucket is known to exist, so the ``HEAD`` is paid once per run and not once
        #: per document.
        self._bucket_ready = False

    def _require_configuration(self) -> None:
        missing = [
            name
            for name, value in (
                ("S3_ENDPOINT_URL", settings.S3_ENDPOINT_URL),
                ("S3_BUCKET_NAME", self.bucket),
                ("S3_ACCESS_KEY", settings.S3_ACCESS_KEY),
                ("S3_SECRET_KEY", settings.S3_SECRET_KEY),
            )
            if not value
        ]
        if missing:
            raise ObjectStorageError(f"S3 não configurado: falta {', '.join(missing)}.")

    def ensure_bucket(self) -> None:
        """
        Confirms the configured bucket exists, creating it only when the operator allowed it.

        Called **once, before the worker touches the queue**, because the failure it guards against
        is not per document: an endpoint that answers ``AccessDenied`` for a bucket that does not
        exist (SeaweedFS does) made every upload of a run look like a credential problem and stamped
        97 documents as failed. Idempotent, so ``upload_file`` calls it too and the ``HEAD`` is paid
        once.
        """
        if self._bucket_ready:
            return
        self._require_configuration()

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if not is_missing_bucket_error(exc):
                raise ObjectStorageError(
                    f"O storage em {settings.S3_ENDPOINT_URL} recusou o bucket '{self.bucket}': {exc}"
                ) from exc
            self._create_bucket()

        self._bucket_ready = True

    def _create_bucket(self) -> None:
        if not settings.S3_AUTO_CREATE_BUCKET:
            raise ObjectStorageError(
                f"O bucket '{self.bucket}' não existe em {settings.S3_ENDPOINT_URL} e "
                "S3_AUTO_CREATE_BUCKET está desligado. Crie o bucket antes de rodar o worker "
                f"(por exemplo: aws s3 mb s3://{self.bucket} --endpoint-url {settings.S3_ENDPOINT_URL}) "
                "ou defina S3_AUTO_CREATE_BUCKET=true para que o próprio worker o crie."
            )

        try:
            self.client.create_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if not is_already_exists_error(exc):
                raise ObjectStorageError(
                    f"Não foi possível criar o bucket '{self.bucket}' em {settings.S3_ENDPOINT_URL}: {exc}"
                ) from exc
        else:
            logger.info(
                f"🪣 Created bucket '{self.bucket}' at {settings.S3_ENDPOINT_URL} (S3_AUTO_CREATE_BUCKET=true)."
            )

    def read_object(self, uri: str) -> tuple[bytes, str] | None:
        """
        Reads one stored object, by the URI the archive wrote: ``(bytes, media_type)`` or ``None``.

        ``None`` is the **expected** answer for a row whose object is gone — the URI is a reference
        and not a guarantee — and the API maps it to a 404 while the dossier shows a placeholder.
        A malformed URI is also ``None``, because there is nothing to read and the defect belongs in
        the log, not in a 500 answered to an ``<img>``. A failure that is *not* a missing key — an
        unreachable endpoint, a refused credential — raises ``ObjectStorageError`` instead: that one
        is an operator problem and the API answers 503.

        Only ``image/*`` is served. The worker writes JPEG and the bucket's ``ContentType`` could say
        anything; thinking otherwise would let the object storage decide the media type of a response
        the API serves from its own origin.
        """
        try:
            bucket, key = parse_s3_uri(uri)
        except ValueError:
            logger.warning(f"🖼️ Ignoring a malformed storage URI: {uri!r}")
            return None

        self._require_configuration()
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if is_missing_object_error(exc):
                logger.warning(f"🖼️ Stored object is gone: {uri}")
                return None
            raise ObjectStorageError(f"O storage em {settings.S3_ENDPOINT_URL} não leu '{uri}': {exc}") from exc

        body = response["Body"].read()
        media_type = str(response.get("ContentType") or "")
        if not media_type.startswith("image/"):
            media_type = "image/jpeg"
        return body, media_type

    def upload_file(self, file_stream: BytesIO, file_path: str, content_type: str = "image/jpeg") -> str:
        try:
            self.ensure_bucket()
            self.client.upload_fileobj(file_stream, self.bucket, file_path, ExtraArgs={"ContentType": content_type})
            return f"s3://{self.bucket}/{file_path}"
        except Exception as e:
            logger.error(f"❌ Error uploading file to S3: {e}")
            raise
