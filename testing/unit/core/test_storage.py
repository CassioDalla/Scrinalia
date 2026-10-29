"""The bucket is confirmed before the first upload, and the failure names the real cause.

A missing bucket is not a credential problem, but an S3-compatible endpoint does not always say so:
SeaweedFS answers ``AccessDenied`` to a ``PutObject`` into a bucket that does not exist. That is the
failure this module pins — the worker used to record it once per document and stamp the whole
backlog, and the operator went looking for a wrong password. ``S3_AUTO_CREATE_BUCKET`` is off by
default on purpose: object storage is infrastructure the operator brings, and the app creates it
only when told to.
"""

from io import BytesIO

import pytest
from botocore.exceptions import ClientError
from pydantic import SecretStr

from scrinalia.core import config as config_module
from scrinalia.core import storage as storage_module
from scrinalia.core.config import missing_storage_settings, storage_configured
from scrinalia.core.storage import (
    ObjectStorageError,
    S3Storage,
    is_missing_bucket_error,
    is_missing_object_error,
    parse_s3_uri,
)


def _client_error(code: str, status: int, operation: str = "HeadBucket") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        operation,
    )


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class _FakeClient:
    """A boto3 client double that counts what the storage asked of it."""

    def __init__(
        self,
        head_error: ClientError | None = None,
        create_error: ClientError | None = None,
        get_error: ClientError | None = None,
        body: bytes = b"",
        content_type: str = "image/jpeg",
    ) -> None:
        self.head_error = head_error
        self.create_error = create_error
        self.get_error = get_error
        self.body = body
        self.content_type = content_type
        self.heads = 0
        self.creates = 0
        self.uploads = 0
        self.gets: list[tuple[str, str]] = []

    def head_bucket(self, Bucket: str) -> None:
        self.heads += 1
        if self.head_error is not None:
            raise self.head_error

    def create_bucket(self, Bucket: str) -> None:
        self.creates += 1
        if self.create_error is not None:
            raise self.create_error

    def upload_fileobj(self, file_stream, bucket, key, ExtraArgs=None) -> None:
        self.uploads += 1

    def get_object(self, Bucket: str, Key: str) -> dict:
        self.gets.append((Bucket, Key))
        if self.get_error is not None:
            raise self.get_error
        return {"Body": _FakeBody(self.body), "ContentType": self.content_type}


def _storage(
    monkeypatch, client: _FakeClient, *, auto_create: bool = False, bucket: str | None = "thumbs"
) -> S3Storage:
    monkeypatch.setattr(storage_module.settings, "S3_ENDPOINT_URL", "http://storage.local:8333")
    monkeypatch.setattr(storage_module.settings, "S3_BUCKET_NAME", bucket)
    monkeypatch.setattr(storage_module.settings, "S3_ACCESS_KEY", SecretStr("chave"))
    monkeypatch.setattr(storage_module.settings, "S3_SECRET_KEY", SecretStr("segredo"))
    monkeypatch.setattr(storage_module.settings, "S3_AUTO_CREATE_BUCKET", auto_create)
    monkeypatch.setattr(storage_module.boto3, "client", lambda *args, **kwargs: client)
    return S3Storage()


def test_ensure_bucket_is_a_no_op_when_the_bucket_is_there(monkeypatch) -> None:
    client = _FakeClient()
    storage = _storage(monkeypatch, client)

    storage.ensure_bucket()

    assert client.heads == 1
    assert client.creates == 0


def test_ensure_bucket_refuses_a_missing_bucket_and_names_the_way_out(monkeypatch) -> None:
    """With the flag off, the refusal is one sentence that says what to create and how to allow it."""
    client = _FakeClient(head_error=_client_error("404", 404))
    storage = _storage(monkeypatch, client, auto_create=False)

    with pytest.raises(ObjectStorageError) as refusal:
        storage.ensure_bucket()

    sentence = str(refusal.value)
    assert "thumbs" in sentence
    assert "S3_AUTO_CREATE_BUCKET=true" in sentence
    assert client.creates == 0, "the app must not provision the operator's storage unless told to"


def test_ensure_bucket_creates_it_when_the_operator_allowed_it(monkeypatch) -> None:
    client = _FakeClient(head_error=_client_error("404", 404))
    storage = _storage(monkeypatch, client, auto_create=True)

    storage.ensure_bucket()

    assert client.creates == 1


def test_ensure_bucket_tolerates_the_race_that_created_it_first(monkeypatch) -> None:
    """Somebody else creating the bucket between our HEAD and our CREATE is success, not a failure."""
    client = _FakeClient(
        head_error=_client_error("404", 404),
        create_error=_client_error("BucketAlreadyOwnedByYou", 409, "CreateBucket"),
    )
    storage = _storage(monkeypatch, client, auto_create=True)

    storage.ensure_bucket()

    assert client.creates == 1


def test_ensure_bucket_surfaces_an_error_that_is_not_a_missing_bucket(monkeypatch) -> None:
    """``AccessDenied`` on the HEAD is a credentials/permission problem and must not be mistaken for one."""
    client = _FakeClient(head_error=_client_error("AccessDenied", 403))
    storage = _storage(monkeypatch, client, auto_create=True)

    with pytest.raises(ObjectStorageError, match="AccessDenied"):
        storage.ensure_bucket()

    assert client.creates == 0


def test_ensure_bucket_refuses_an_unconfigured_endpoint(monkeypatch) -> None:
    client = _FakeClient()
    storage = _storage(monkeypatch, client, bucket=None)

    with pytest.raises(ObjectStorageError, match="S3 não configurado"):
        storage.ensure_bucket()

    assert client.heads == 0


def test_upload_file_pays_the_head_once_across_uploads(monkeypatch) -> None:
    """The check is per run, not per document: 97 documents must not mean 97 HEADs."""
    client = _FakeClient(head_error=_client_error("404", 404))
    storage = _storage(monkeypatch, client, auto_create=True)

    storage.upload_file(BytesIO(b"a"), "thumbnails/a.jpg")
    storage.upload_file(BytesIO(b"b"), "thumbnails/b.jpg")

    assert client.heads == 1
    assert client.creates == 1
    assert client.uploads == 2


@pytest.mark.parametrize("code,status", [("404", 404), ("NoSuchBucket", 404), ("NotFound", 404)])
def test_missing_bucket_classification_covers_the_endpoints(code: str, status: int) -> None:
    assert is_missing_bucket_error(_client_error(code, status)) is True


def test_a_permission_error_is_not_a_missing_bucket() -> None:
    assert is_missing_bucket_error(_client_error("AccessDenied", 403)) is False


# ==========================================
# READING ONE OBJECT (the thumbnail route)
# ==========================================


def test_parse_s3_uri_splits_bucket_and_key() -> None:
    assert parse_s3_uri("s3://meu-bucket-teste/thumbnails/thumb_109222.jpg") == (
        "meu-bucket-teste",
        "thumbnails/thumb_109222.jpg",
    )


@pytest.mark.parametrize(
    "uri",
    ["", "thumb_1.jpg", "https://bucket/key.jpg", "s3://bucket", "s3:///key.jpg"],
)
def test_parse_s3_uri_refuses_anything_that_is_not_a_complete_reference(uri: str) -> None:
    with pytest.raises(ValueError):
        parse_s3_uri(uri)


def test_read_object_returns_the_bytes_and_the_media_type(monkeypatch) -> None:
    client = _FakeClient(body=b"\xff\xd8jpeg", content_type="image/jpeg")
    storage = _storage(monkeypatch, client)

    stored = storage.read_object("s3://thumbs/thumbnails/thumb_1.jpg")

    assert stored == (b"\xff\xd8jpeg", "image/jpeg")
    # The bucket comes from the URI, not from ``S3_BUCKET_NAME``: a row written before the
    # installation moved still names the object it stored.
    assert client.gets == [("thumbs", "thumbnails/thumb_1.jpg")]


def test_read_object_serves_images_only(monkeypatch) -> None:
    """Whatever the bucket's metadata says, this origin never answers with a non-image type."""
    client = _FakeClient(body=b"<html>", content_type="text/html")
    storage = _storage(monkeypatch, client)

    assert storage.read_object("s3://thumbs/a.jpg") == (b"<html>", "image/jpeg")


@pytest.mark.parametrize("code,status", [("NoSuchKey", 404), ("404", 404), ("NoSuchBucket", 404)])
def test_read_object_answers_none_when_the_object_is_gone(monkeypatch, code: str, status: int) -> None:
    client = _FakeClient(get_error=_client_error(code, status, "GetObject"))
    storage = _storage(monkeypatch, client)

    assert storage.read_object("s3://thumbs/gone.jpg") is None
    assert is_missing_object_error(_client_error(code, status)) is True


def test_read_object_raises_when_the_endpoint_is_not_a_missing_object(monkeypatch) -> None:
    client = _FakeClient(get_error=_client_error("AccessDenied", 403, "GetObject"))
    storage = _storage(monkeypatch, client)

    with pytest.raises(ObjectStorageError, match="AccessDenied"):
        storage.read_object("s3://thumbs/a.jpg")


def test_read_object_ignores_a_malformed_uri_instead_of_reading_it(monkeypatch) -> None:
    client = _FakeClient(body=b"bytes")
    storage = _storage(monkeypatch, client)

    assert storage.read_object("s3://") is None
    assert client.gets == []


# ==========================================
# "CONFIGURED" HAS ONE DEFINITION (#258)
# ==========================================


def _configure_storage(monkeypatch) -> None:
    """Sets all four settings on the shared object every reader imports."""
    monkeypatch.setattr(config_module.settings, "S3_ENDPOINT_URL", "http://storage.local:8333")
    monkeypatch.setattr(config_module.settings, "S3_BUCKET_NAME", "thumbs")
    monkeypatch.setattr(config_module.settings, "S3_ACCESS_KEY", SecretStr("chave"))
    monkeypatch.setattr(config_module.settings, "S3_SECRET_KEY", SecretStr("segredo"))


def test_all_four_storage_settings_configure_it(monkeypatch) -> None:
    _configure_storage(monkeypatch)

    assert storage_configured() is True
    assert missing_storage_settings() == []


@pytest.mark.parametrize("name", ["S3_ENDPOINT_URL", "S3_BUCKET_NAME", "S3_ACCESS_KEY", "S3_SECRET_KEY"])
def test_any_of_the_four_settings_missing_leaves_the_storage_unconfigured(monkeypatch, name: str) -> None:
    _configure_storage(monkeypatch)
    monkeypatch.setattr(config_module.settings, name, None)

    assert missing_storage_settings() == [name]
    assert storage_configured() is False


def test_an_empty_credential_counts_as_missing(monkeypatch) -> None:
    """The probe used ``is None`` while the reader used truthiness; the predicate settles it."""
    _configure_storage(monkeypatch)
    monkeypatch.setattr(config_module.settings, "S3_ACCESS_KEY", SecretStr(""))

    assert missing_storage_settings() == ["S3_ACCESS_KEY"]
    assert storage_configured() is False


def test_the_client_is_built_on_first_use_and_not_at_construction(monkeypatch) -> None:
    """A page of miniatures pays one client; an unconfigured installation pays none."""
    client = _FakeClient()
    _configure_storage(monkeypatch)
    built: list[_FakeClient] = []

    def build(*args, **kwargs) -> _FakeClient:
        built.append(client)
        return client

    monkeypatch.setattr(storage_module.boto3, "client", build)

    storage = S3Storage()
    assert built == []

    storage.ensure_bucket()
    assert built == [client]


def test_no_client_is_built_when_the_storage_is_unconfigured(monkeypatch) -> None:
    """``read_object`` must refuse before boto3 — the route's 404 cannot pay a client per image."""
    _configure_storage(monkeypatch)
    monkeypatch.setattr(config_module.settings, "S3_BUCKET_NAME", None)
    built: list[object] = []

    def build(*args, **kwargs) -> object:
        built.append(object())
        raise AssertionError("boto3.client must not be built for an unconfigured storage")

    monkeypatch.setattr(storage_module.boto3, "client", build)

    storage = S3Storage()
    with pytest.raises(ObjectStorageError, match="S3 não configurado"):
        storage.read_object("s3://thumbs/thumbnails/thumb_1.jpg")

    assert built == []
