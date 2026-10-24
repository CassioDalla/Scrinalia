"""The typology refusal queue read (issue #129).

The queue row is the evidence a run looked at a description and declined; ``typology_id`` NULL
cannot tell that from a description no run reached. These tests drive the read through the route the
screen calls, with the real predicate module behind it, because "the count and the page are the same
question" only means something through the database both read.

The pair that matters most is ``test_the_page_is_the_predicate_and_the_count``: the page, the total
and the bench's count all compose ``repository/typology_queue.py``, and the day one of them drifts
this fails instead of the archivist noticing.
"""

from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
)
from litestar.testing import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveDocument,
    ArchiveReviewStatus,
)
from scrinalia.domains.archive.repository.typology_queue import count_refusals, typology_low_confidence
from scrinalia.domains.identity.domain.permissions import Role


def _refusal(
    db: Session,
    description_id: str,
    *,
    score: float | None = 0.30,
    label: str | None = "Dossiê",
    status: ArchiveReviewStatus = ArchiveReviewStatus.NEEDS_REVIEW,
    payload_title: str = "título do momento da recusa",
) -> None:
    """One refusal row as the typology worker writes it, with only what the read needs."""
    db.add(
        ArchiveAIReviewQueue(
            anomaly_type=AnomalyType.TYPOLOGY_LOW_CONFIDENCE,
            status=status,
            context_payload={"description_id": description_id, "title": payload_title},
            llm_decision=label,
            llm_confidence=score,
        )
    )
    db.flush()


def _page(client: TestClient, **params) -> dict:
    response = client.get("/api/v1/typologies/refusals", params=params)
    assert response.status_code == HTTP_200_OK, response.text
    return response.json()


def _inbox(client: TestClient) -> dict[str, int]:
    response = client.get("/api/v1/curation/inbox")
    assert response.status_code == HTTP_200_OK
    return {queue["key"]: queue["count"] for queue in response.json()["queues"]}


# ==========================================
# THE PAGE IS THE PREDICATE, AND THE COUNT IS THE TOTAL
# ==========================================


def test_the_page_is_the_predicate_and_the_count(
    client: TestClient, api_uses_test_db, db_session: Session, generate_archive_doc, generate_typology
) -> None:
    """The defect of #129, pinned: what the count says is what the list can show."""
    low = generate_archive_doc(description_id="doc-baixa", original_title="Baixa")
    middle = generate_archive_doc(description_id="doc-media", original_title="Média")
    high = generate_archive_doc(description_id="doc-alta", original_title="Alta")
    filed = generate_archive_doc(description_id="doc-arquivada", original_title="Arquivada")
    closed = generate_archive_doc(description_id="doc-fechada", original_title="Fechada")
    other_type = generate_archive_doc(description_id="doc-outro", original_title="Outro tipo")
    typology = generate_typology(id=1, name="Dossiê")

    _refusal(db_session, low.description_id, score=0.05)
    _refusal(db_session, middle.description_id, score=0.30)
    _refusal(db_session, high.description_id, score=0.39)
    _refusal(db_session, filed.description_id, score=0.99)
    _refusal(db_session, closed.description_id, score=0.80, status=ArchiveReviewStatus.AI_APPROVED)
    db_session.add(
        ArchiveAIReviewQueue(
            anomaly_type=AnomalyType.CROSS_DOMAIN_COLLISION,
            status=ArchiveReviewStatus.NEEDS_REVIEW,
            context_payload={"description_id": other_type.description_id},
        )
    )
    filed.typology_id = typology.typology_id
    db_session.flush()

    body = _page(client)

    expected = set(db_session.scalars(select(ArchiveDocument.description_id).where(typology_low_confidence())).all())
    listed = {item["description_id"] for item in body["items"]}
    assert listed == expected == {low.description_id, middle.description_id, high.description_id}
    assert body["total"] == count_refusals(db_session) == 3
    assert _inbox(client)["typology_low_confidence"] == 3

    # Nearest miss first: the population just under the floor is the one that decides the floor.
    assert [item["description_id"] for item in body["items"]] == [
        high.description_id,
        middle.description_id,
        low.description_id,
    ]


def test_a_repeated_run_shows_the_latest_refusal_once(
    client: TestClient, api_uses_test_db, db_session: Session, generate_archive_doc
) -> None:
    """
    ``force`` records a second refusal; the question is about documents, and the evidence is current.

    The older row is deliberately the higher score: picking the maximum would show a number from a
    run whose floor or model may be gone, while the archivist is deciding about the run that just
    refused.
    """
    doc = generate_archive_doc(description_id="doc-duas-vezes", original_title="Recusada duas vezes")
    _refusal(db_session, doc.description_id, score=0.30, label="Ofício")
    _refusal(db_session, doc.description_id, score=0.25, label="Dossiê")

    body = _page(client)

    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["ai_confidence_score"] == 0.25
    assert body["items"][0]["guessed_label"] == "Dossiê"


def test_the_title_comes_from_the_description_not_from_the_payload_snapshot(
    client: TestClient, api_uses_test_db, db_session: Session, generate_archive_doc
) -> None:
    """A rename after the run is what the archivist reads; the queue payload is a snapshot."""
    doc = generate_archive_doc(description_id="doc-renomeada", original_title="Título atual")
    _refusal(db_session, doc.description_id, payload_title="Título antigo")

    body = _page(client)

    assert body["items"][0]["original_title"] == "Título atual"


def test_pagination_is_stable_and_the_clamps_hold(
    client: TestClient, api_uses_test_db, db_session: Session, generate_archive_doc
) -> None:
    """Two pages cover the same set once, and a negative offset does not reach PostgreSQL."""
    for index, score in enumerate((0.10, 0.20, 0.30)):
        doc = generate_archive_doc(description_id=f"doc-pagina-{index}", original_title=f"Página {index}")
        _refusal(db_session, doc.description_id, score=score)

    first = _page(client, limit=2, offset=0)
    second = _page(client, limit=2, offset=2)

    assert first["total"] == second["total"] == 3
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert {item["description_id"] for item in first["items"] + second["items"]} == {
        "doc-pagina-0",
        "doc-pagina-1",
        "doc-pagina-2",
    }

    clamped_low = _page(client, limit=0, offset=-5)
    assert clamped_low["limit"] == 1
    assert clamped_low["offset"] == 0

    clamped_high = _page(client, limit=10_000)
    assert clamped_high["limit"] == 200


# ==========================================
# ACCESS
# ==========================================


def test_the_queue_is_readable_with_a_session_and_not_anonymous(api_client: TestClient, sign_in) -> None:
    """The read is ``AUTHENTICATED``; the write it offers is the dossier's ``CURATE`` command."""
    anonymous = api_client.get("/api/v1/typologies/refusals")
    assert anonymous.status_code == HTTP_401_UNAUTHORIZED

    viewer = sign_in(Role.VIEWER)
    assert viewer.get("/api/v1/typologies/refusals").status_code == HTTP_200_OK

    refused_write = viewer.patch("/api/v1/documents/qualquer-uma", json={"typology_id": 1})
    assert refused_write.status_code == HTTP_403_FORBIDDEN
