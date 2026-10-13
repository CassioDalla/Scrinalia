"""The entity card's badge and the list it opens are the same number (issue #86).

``/entidades/lista`` shows each name with an "N descrições" badge and now expands into those
descriptions. Those are two different reads of **one** definition: the badge counts the link rows
through ``EntityRepository.get_relevance_count`` and the list counts the descriptions through the
``EXISTS`` filter of the collection search (``_carries_entity``). A card promising 647 next to a list
whose ``total`` said 646 is the read lying about the write, and the archivist has no way to tell which
of the two numbers is the true one.

The test drives both through the routes the screen calls, with the real repository: a mocked service
would pin the envelope and say nothing about the two queries agreeing.

The seed carries a description with **two** entities of the same type on purpose. The two filters are
``EXISTS`` predicates and not joins, so that description counts once in the badge and once in the list;
a join would answer 2 where the card promises 1, which is the drift ``EXISTS`` exists to prevent. The
same reasoning is pinned for the drawer's tags in ``test_category_documents.py``.
"""

from litestar.status_codes import HTTP_200_OK
from litestar.testing import TestClient
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveDocumentEntity, ArchiveEntity


def _seed(db_session: Session) -> tuple[ArchiveEntity, ArchiveEntity]:
    """Two organisations: one carried by two descriptions, one carried by a third."""
    urbanismo = ArchiveEntity(name="Secretaria Municipal do Urbanismo", entity_type="ORG")
    fundacao = ArchiveEntity(name="Fundação Cultural de Curitiba", entity_type="ORG")
    db_session.add_all([urbanismo, fundacao])
    db_session.flush()
    return urbanismo, fundacao


def _badge(client: TestClient, entity_id: int) -> int:
    """The weight the card shows, read from the route the card calls."""
    response = client.get("/api/v1/taxonomy/entities/relevance?limit=50")
    assert response.status_code == HTTP_200_OK
    row = next(item for item in response.json()["data"] if item["entity_id"] == entity_id)
    return int(row["total_usage"])


def test_the_badge_and_the_expansion_total_are_the_same_number(
    client: TestClient, api_uses_test_db, db_session: Session, generate_archive_doc
) -> None:
    urbanismo, fundacao = _seed(db_session)

    heavy = generate_archive_doc(original_title="Um nome, e outro da mesma espécie")
    light = generate_archive_doc(original_title="Só o primeiro nome")
    elsewhere = generate_archive_doc(original_title="Só o segundo nome")
    db_session.add_all(
        [
            # Two entities of the same type on one description: the row the join would multiply.
            ArchiveDocumentEntity(description_id=heavy.description_id, entity_id=urbanismo.entity_id),
            ArchiveDocumentEntity(description_id=heavy.description_id, entity_id=fundacao.entity_id),
            ArchiveDocumentEntity(description_id=light.description_id, entity_id=urbanismo.entity_id),
            ArchiveDocumentEntity(description_id=elsewhere.description_id, entity_id=fundacao.entity_id),
        ]
    )
    db_session.flush()

    badge = _badge(client, urbanismo.entity_id)
    # Two descriptions, not three links: the card's weight is documents, not spellings.
    assert badge == 2

    listing = client.get(f"/api/v1/documents?entity_id={urbanismo.entity_id}&limit=10&offset=0")
    assert listing.status_code == HTTP_200_OK
    body = listing.json()
    assert body["total"] == badge
    assert {item["description_id"] for item in body["items"]} == {heavy.description_id, light.description_id}

    # The total is the count of the result set, not of the page: it must not move with the offset.
    page = client.get(f"/api/v1/documents?entity_id={urbanismo.entity_id}&limit=1&offset=1").json()
    assert page["total"] == badge
    assert len(page["items"]) == 1


def test_an_orphan_is_not_ranked_and_its_expansion_is_empty(
    client: TestClient, api_uses_test_db, db_session: Session, generate_archive_doc
) -> None:
    """An entity no description carries: no card in the ranking, and an empty page if one is asked for.

    Measured rather than assumed, and it is the half that matters for the screen: the ranking
    (``GET /entities/relevance``) inner-joins the link table and **drops** an entity nobody carries, so
    the "sem descrições" state of the expansion is defensive — reached through a stale page, a shared
    link or the clipboard, not through this list. What must hold either way is that the read the
    expansion uses answers zero and an empty page instead of an error, which is what the card needs in
    order to say so explicitly.
    """
    orphan = ArchiveEntity(name="Nome Sem Lastro", entity_type="ORG")
    other = ArchiveEntity(name="Nome Com Lastro", entity_type="ORG")
    db_session.add_all([orphan, other])
    db_session.flush()

    # A description exists and carries the other name, so an empty answer cannot come from an empty table.
    document = generate_archive_doc(original_title="Uma descrição qualquer")
    db_session.add(ArchiveDocumentEntity(description_id=document.description_id, entity_id=other.entity_id))
    db_session.flush()

    ranking = client.get("/api/v1/taxonomy/entities/relevance?limit=50")
    assert ranking.status_code == HTTP_200_OK
    assert orphan.entity_id not in {row["entity_id"] for row in ranking.json()["data"]}

    listing = client.get(f"/api/v1/documents?entity_id={orphan.entity_id}&limit=10&offset=0")
    assert listing.status_code == HTTP_200_OK
    body = listing.json()
    assert body["total"] == 0
    assert body["items"] == []
