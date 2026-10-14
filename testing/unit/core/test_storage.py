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

from scrinalia.core import storage as storage_module
from scrinalia.core.storage import ObjectStorageError, S3Storage, is_missing_bucket_error


def _client_error(code: str, status: int, operation: str = "HeadBucket") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        operation,
    )


class _FakeClient:
    """A boto3 client double that counts what the storage asked of it."""

    def __init__(self, head_error: ClientError | None = None, create_error: ClientError | None = None) -> None:
        self.head_error = head_error
        self.create_error = create_error
        self.heads = 0
        self.creates = 0
        self.uploads = 0

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
