"""The language catalogue over HTTP: the one read the form and the dossier share."""

from litestar.status_codes import HTTP_200_OK
from litestar.testing import TestClient

from scrinalia.domains.archive.domain.language_catalog import LANGUAGES


def test_the_catalogue_is_published_in_the_order_the_select_shows(client: TestClient) -> None:
    response = client.get("/api/v1/languages")

    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert [item["name"] for item in body] == [language.name for language in LANGUAGES]
    assert body[0] == {"code": "pt", "name": "Português"}


def test_the_endpoint_is_read_only(client: TestClient) -> None:
    """
    Adding a language is a line in the catalogue, not a request.

    The route is read-only by design: a language carries no rule an institution edits, unlike a
    typology (a candidate label for the classifier) or a rung (which states whether it requires a
    parent). Asserting the refusal here keeps a future ``POST`` from landing unnoticed.
    """
    response = client.post("/api/v1/languages", json={"code": "xx", "name": "Novo"})

    assert response.status_code == 405
