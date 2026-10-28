"""The access-point preview route: the reading the manual form shows before it saves.

The route is read-only by design; the tests pin the statuses the form consumes and that answering
them adds no tag row.
"""

from litestar.status_codes import HTTP_200_OK
from litestar.testing import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveTag, DomainStopwords, DomainSynonyms
from scrinalia.domains.archive.models.enums import StopwordsScope


def _seed(db: Session) -> ArchiveTag:
    urbanismo = ArchiveTag(name="urbanismo")
    db.add(urbanismo)
    db.flush()
    db.add(DomainSynonyms(category="TAG", synonym_name="urbanismos", canonical_tag_id=urbanismo.tag_id))
    db.add(DomainStopwords(word="obras", word_scope=StopwordsScope.TAG, source="HUMAN"))
    db.flush()
    return urbanismo


def _preview(client: TestClient, indexing_points: str | None) -> list[dict]:
    response = client.post("/api/v1/taxonomy/tags/preview", json={"indexing_points": indexing_points})
    assert response.status_code == HTTP_200_OK, response.text
    return response.json()["items"]


def test_the_preview_answers_the_statuses_the_form_shows(client: TestClient, db_session: Session) -> None:
    urbanismo = _seed(db_session)

    items = _preview(client, "Urbanismo, urbanismos, obras, ab, Novo Termo, Novo Termo")

    assert [(item["input"], item["status"], item["name"], item["tag_id"]) for item in items] == [
        ("Urbanismo", "EXISTING", "urbanismo", urbanismo.tag_id),
        ("urbanismos", "SYNONYM", "urbanismo", urbanismo.tag_id),
        ("obras", "STOPWORD", None, None),
        ("ab", "TOO_SHORT", None, None),
        ("Novo Termo", "NEW", "novo termo", None),
        ("Novo Termo", "DUPLICATE", None, None),
    ]
    assert list(db_session.scalars(select(ArchiveTag.name)).all()) == ["urbanismo"]


def test_the_preview_accepts_an_empty_body_and_writes_nothing(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/v1/taxonomy/tags/preview", json={})

    assert response.status_code == HTTP_200_OK
    assert response.json()["items"] == []
    assert list(db_session.scalars(select(ArchiveTag.name)).all()) == []
