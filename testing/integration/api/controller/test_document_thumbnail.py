"""The miniature the dossier shows: one authenticated route, advertised by the read view.

These tests pin the three states the screen draws — the bytes, "no image" and "the object is gone" —
and the one property that makes the SPA's ``<img>`` possible without a hand-built URL: the URL in
``DocumentSummary.thumbnail_url`` is served by the application. The bucket is a dictionary here: the
point is the HTTP contract, not boto3, which ``testing/unit/core/test_storage.py`` covers.
"""

import pytest
from litestar.testing import TestClient

from scrinalia.core.storage import ObjectStorageError


class _FakeStorage:
    """What ``S3Storage`` looks like to the route: one URI in, the bytes or ``None`` out."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.error: Exception | None = None

    def read_object(self, uri: str) -> tuple[bytes, str] | None:
        if self.error is not None:
            raise self.error
        return self.objects.get(uri)


@pytest.fixture()
def thumbnail_storage(monkeypatch):
    """Replaces the process-wide reader and clears the cache the provider holds it in."""
    from scrinalia.api import dependencies

    storage = _FakeStorage()
    monkeypatch.setattr("scrinalia.core.storage.S3Storage", lambda: storage)
    dependencies.provide_thumbnail_reader.cache_clear()
    yield storage
    dependencies.provide_thumbnail_reader.cache_clear()


def test_the_summary_advertises_a_url_the_route_actually_serves(
    client: TestClient, generate_archive_doc, thumbnail_storage: _FakeStorage
) -> None:
    """The pin between the contract and the route: the advertised URL answers 200, not a 404."""
    uri = "s3://thumbs/thumbnails/thumb_1.jpg"
    document = generate_archive_doc(storage_thumbnail_uri=uri)
    thumbnail_storage.objects[uri] = (b"\xff\xd8jpeg-bytes", "image/jpeg")

    summary = client.get(f"/api/v1/documents/{document.description_id}")
    assert summary.status_code == 200
    url = summary.json()["thumbnail_url"]
    assert url == f"/api/v1/documents/{document.description_id}/thumbnail"

    response = client.get(url)
    assert response.status_code == 200
    assert response.content == b"\xff\xd8jpeg-bytes"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=300"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_the_list_advertises_the_same_url(
    client: TestClient, generate_archive_doc, thumbnail_storage: _FakeStorage
) -> None:
    """The list card draws the miniature too, so the page carries the URL as well."""
    document = generate_archive_doc(storage_thumbnail_uri="s3://thumbs/thumbnails/thumb_2.jpg")

    response = client.get("/api/v1/documents/?limit=50")

    assert response.status_code == 200
    item = next(row for row in response.json()["items"] if row["description_id"] == document.description_id)
    assert item["thumbnail_url"] == f"/api/v1/documents/{document.description_id}/thumbnail"


def test_a_description_without_a_stored_image_has_no_url_and_answers_404(
    client: TestClient, generate_archive_doc
) -> None:
    """Four of the reference collection's 101 descriptions are this case, not an edge."""
    document = generate_archive_doc()

    summary = client.get(f"/api/v1/documents/{document.description_id}")
    assert summary.status_code == 200
    assert summary.json()["thumbnail_url"] is None

    assert client.get(f"/api/v1/documents/{document.description_id}/thumbnail").status_code == 404


def test_an_object_that_left_the_bucket_answers_404_not_a_broken_image(
    client: TestClient, generate_archive_doc, thumbnail_storage: _FakeStorage
) -> None:
    """The URI is a reference, not a guarantee: the bucket may no longer hold the object."""
    document = generate_archive_doc(storage_thumbnail_uri="s3://thumbs/thumbnails/gone.jpg")

    response = client.get(f"/api/v1/documents/{document.description_id}/thumbnail")

    assert response.status_code == 404
    assert thumbnail_storage.objects == {}


def test_a_missing_description_answers_404(client: TestClient) -> None:
    assert client.get("/api/v1/documents/nao-existe/thumbnail").status_code == 404


def test_the_route_is_closed_to_anonymous_readers(api_client: TestClient) -> None:
    """An ``<img>`` sends the session cookie; without one the answer is 401, not the bytes."""
    assert api_client.get("/api/v1/documents/doc-1/thumbnail").status_code == 401


def test_an_unreachable_storage_is_503_and_not_a_broken_image(
    client: TestClient, generate_archive_doc, thumbnail_storage: _FakeStorage
) -> None:
    """Credentials, endpoint or bucket are an operator problem; the screen still renders."""
    document = generate_archive_doc(storage_thumbnail_uri="s3://thumbs/thumbnails/thumb_3.jpg")
    thumbnail_storage.error = ObjectStorageError("S3 não configurado")

    response = client.get(f"/api/v1/documents/{document.description_id}/thumbnail")

    assert response.status_code == 503
