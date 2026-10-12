"""The tag catalogue read, and the decisions it takes (issue #64).

The card on the home screen promised a queue and the screen it opened could not show it: the tag
catalog had four tabs, none of which carried the drawer state, and the only read that mentioned a
category was the type-ahead — which requires a term and hands back a top-N by weight. These tests
pin what replaced it, and they are driven through the routes the screen calls with the real
repository, because "the card's number is the list's ``total``" only means something through the
database both read.

The pair that matters most is ``test_the_orphan_card_and_the_pending_list_are_the_same_number``: the
count and the page come from the same predicate module (``repository/subject_queue.py``), and the
day one of them drifts this fails instead of the archivist noticing.
"""

from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.testing import TestClient
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveMacroCategory,
    ArchiveReviewStatus,
    ArchiveTag,
    ArchiveTagFacet,
    DomainSubjectExclusion,
    TagFacetType,
)

# ==========================================
# SEED
# ==========================================


def _category(db: Session, name: str = "Urbanismo") -> ArchiveMacroCategory:
    category = ArchiveMacroCategory(name=name, description=None, classifier_label=None, is_active=True)
    db.add(category)
    db.flush()
    return category


def _tag(db: Session, name: str, **kwargs) -> ArchiveTag:
    tag = ArchiveTag(name=name, **kwargs)
    db.add(tag)
    db.flush()
    return tag


def _queue(db: Session, tag_id: int, status: ArchiveReviewStatus = ArchiveReviewStatus.NEEDS_REVIEW) -> None:
    db.add(
        ArchiveAIReviewQueue(
            anomaly_type=AnomalyType.SUBJECT_LOW_CONFIDENCE,
            status=status,
            context_payload={"tag_id": tag_id, "tag_name": f"#{tag_id}"},
        )
    )
    db.flush()


def _catalog(client: TestClient, **params) -> dict:
    query = "&".join(f"{key}={value}" for key, value in params.items() if value is not None)
    response = client.get(f"/api/v1/taxonomy/tags/catalog?{query}")
    assert response.status_code == HTTP_200_OK, response.text
    return response.json()


def _inbox(client: TestClient) -> dict[str, int]:
    response = client.get("/api/v1/curation/inbox")
    assert response.status_code == HTTP_200_OK
    return {queue["key"]: queue["count"] for queue in response.json()["queues"]}


# ==========================================
# THE NUMBER THE CARD PROMISES IS THE LIST'S TOTAL
# ==========================================


def test_the_orphan_card_and_the_pending_list_are_the_same_number(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """The defect of #64, pinned: what the card counts is what the screen it opens can show."""
    category = _category(db_session)
    _tag(db_session, "urbanismo", macro_category_id=category.category_id)
    _tag(db_session, "alvenaria")
    _tag(db_session, "zoneamento")
    _tag(db_session, "cidade")
    db_session.add(DomainSubjectExclusion(term="cidade", source="HUMAN"))
    db_session.flush()
    facade = _tag(db_session, "alfa")
    db_session.add(ArchiveTagFacet(tag_id=facade.tag_id, facet_type=TagFacetType.INSTITUTION.value, value="alfa"))
    db_session.flush()

    pending = _catalog(client, subject_state="PENDING", limit=25)
    assert pending["total"] == _inbox(client)["orphan_subject_tags"] == 2
    assert {row["name"] for row in pending["items"]} == {"alvenaria", "zoneamento"}

    # And the slice showed the whole catalogue, not a top-N: the decided tags are still listed,
    # each one explaining its own state.
    everything = _catalog(client, subject_state="ALL", limit=25)
    assert everything["total"] == 5
    by_name = {row["name"]: row for row in everything["items"]}
    assert by_name["urbanismo"]["macro_category_name"] == "Urbanismo"
    assert by_name["cidade"]["subject_excluded"] is True
    assert by_name["alfa"]["facets"] == ["INSTITUTION"]


def test_the_decision_states_partition_the_catalogue(client: TestClient, api_uses_test_db, db_session: Session) -> None:
    """A tag is in exactly one of the three undecided/decided slices, plus the drawers."""
    category = _category(db_session)
    _tag(db_session, "com-categoria", macro_category_id=category.category_id)
    _tag(db_session, "pendente-1")
    _tag(db_session, "pendente-2")
    db_session.add(DomainSubjectExclusion(term="nao-assunto", source="HUMAN"))
    _tag(db_session, "nao-assunto")
    place = _tag(db_session, "lugar")
    db_session.add(ArchiveTagFacet(tag_id=place.tag_id, facet_type=TagFacetType.PLACE.value, value="lugar"))
    db_session.flush()

    total = _catalog(client, subject_state="ALL", limit=25)["total"]
    slices = {
        state: _catalog(client, subject_state=state, limit=25)["total"] for state in ("PENDING", "NOT_SUBJECT", "FACET")
    }

    assert slices == {"PENDING": 2, "NOT_SUBJECT": 1, "FACET": 1}
    assert sum(slices.values()) == total - 1  # the one tag in a drawer


def test_the_low_confidence_card_counts_tags_not_queue_rows(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """
    Two runs that queued the same tag are one decision to take, and a decided tag is none.

    ``worker_macro_category`` inserts a row per run whose label set changed, and nothing deletes the
    row when a human files the tag: the card has to count the *tags* whose work is still open.
    """
    first = _tag(db_session, "incerta")
    second = _tag(db_session, "tambem-incerta")
    _queue(db_session, first.tag_id)
    _queue(db_session, first.tag_id)  # the same tag, queued by a second run
    _queue(db_session, second.tag_id)
    db_session.flush()

    assert _catalog(client, subject_state="LOW_CONFIDENCE", limit=25)["total"] == 2
    assert _inbox(client)["subject_low_confidence"] == 2

    # Filing one tag answers its question, even though its queue row is still there.
    category = _category(db_session, "Saúde")
    answered = client.patch(f"/api/v1/taxonomy/tags/{second.tag_id}", json={"macro_category_id": category.category_id})
    assert answered.status_code == HTTP_200_OK

    assert _catalog(client, subject_state="LOW_CONFIDENCE", limit=25)["total"] == 1
    assert _inbox(client)["subject_low_confidence"] == 1


# ==========================================
# THE WRITES, AND THE STATE EACH ONE SETTLES
# ==========================================


def test_declaring_not_a_subject_is_durable_and_deletes_nothing(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """
    ``null`` is a verdict, and the verdict outlives the next classifier run.

    ``worker_macro_category`` re-queues a tag whose drawer is empty every time the label set
    changes, so the column alone is not the decision — ``domain_subject_exclusions`` is what the
    worker obeys. The tag itself is untouched: only the subject axis stops guessing at it.
    """
    tag = _tag(db_session, "pessoas")
    db_session.flush()

    response = client.patch(f"/api/v1/taxonomy/tags/{tag.tag_id}", json={"macro_category_id": None})
    assert response.status_code == HTTP_200_OK
    body = response.json()
    assert body["macro_category_id"] is None
    assert body["subject_excluded"] is True

    excluded = client.get("/api/v1/taxonomy/tags/subject-exclusions")
    assert excluded.status_code == HTTP_200_OK
    assert excluded.json() == ["pessoas"]

    # Out of the queue, still in the collection: the total of the catalogue does not move.
    assert _catalog(client, subject_state="PENDING", limit=25)["total"] == 0
    assert _catalog(client, subject_state="NOT_SUBJECT", limit=25)["total"] == 1
    assert _catalog(client, subject_state="ALL", limit=25)["total"] == 1
    assert _inbox(client)["orphan_subject_tags"] == 0


def test_filing_a_tag_takes_it_off_the_non_subject_axis(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """A tag in a drawer is not also a term the classifier must skip, nor a place *instead*."""
    category = _category(db_session)
    tag = _tag(db_session, "centro")
    db_session.add(DomainSubjectExclusion(term="centro", source="HUMAN"))
    db_session.add(ArchiveTagFacet(tag_id=tag.tag_id, facet_type=TagFacetType.PLACE.value, value="centro"))
    db_session.flush()

    response = client.patch(f"/api/v1/taxonomy/tags/{tag.tag_id}", json={"macro_category_id": category.category_id})
    assert response.status_code == HTTP_200_OK
    assert response.json()["subject_excluded"] is False

    everything = _catalog(client, subject_state="ALL", limit=25)
    row = next(item for item in everything["items"] if item["tag_id"] == tag.tag_id)
    assert row["macro_category_id"] == category.category_id
    assert row["facets"] == []
    assert row["subject_excluded"] is False
    assert client.get("/api/v1/taxonomy/tags/subject-exclusions").json() == []


def test_declaring_a_facet_settles_the_whole_state_and_can_be_undone(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """
    The third destination: a producer or a place, which is what lets the queue reach zero.

    The declaration leaves the drawer (a facet is what the tag is *instead* of a subject) and joins
    the subject exclusion, so the classifier does not guess at it either. Removing it puts the tag
    back in the queue — the exclusion goes with the last facet, because keeping it would park the
    tag in "goes nowhere", a decision nobody took.
    """
    category = _category(db_session)
    tag = _tag(db_session, "alfa", macro_category_id=category.category_id)
    db_session.flush()

    declared = client.put(f"/api/v1/taxonomy/tags/{tag.tag_id}/facets/{TagFacetType.INSTITUTION.value}", json={})
    assert declared.status_code == HTTP_200_OK, declared.text
    body = declared.json()
    assert body["facets"] == ["INSTITUTION"]
    assert body["macro_category_id"] is None
    assert body["subject_excluded"] is True

    assert _catalog(client, subject_state="FACET", limit=25)["total"] == 1
    assert _catalog(client, subject_state="PENDING", limit=25)["total"] == 0
    assert _inbox(client)["orphan_subject_tags"] == 0

    removed = client.delete(f"/api/v1/taxonomy/tags/{tag.tag_id}/facets/{TagFacetType.INSTITUTION.value}")
    assert removed.status_code == HTTP_200_OK
    assert removed.json()["facets"] == []
    assert removed.json()["subject_excluded"] is False
    # Back in the queue, undecided again: the undo restores the state before the declaration.
    assert _catalog(client, subject_state="PENDING", limit=25)["total"] == 1
    assert _inbox(client)["orphan_subject_tags"] == 1


def test_a_tag_can_carry_a_place_and_an_institution(client: TestClient, api_uses_test_db, db_session: Session) -> None:
    """The table's primary key says a tag can be both; the read and the undo must respect it."""
    tag = _tag(db_session, "prefeitura")
    db_session.flush()

    for facet in (TagFacetType.PLACE, TagFacetType.INSTITUTION):
        response = client.put(f"/api/v1/taxonomy/tags/{tag.tag_id}/facets/{facet.value}", json={"value": "PMC"})
        assert response.status_code == HTTP_200_OK

    listed = client.get("/api/v1/taxonomy/tags/catalog?subject_state=FACET")
    assert listed.status_code == HTTP_200_OK
    assert listed.json()["items"][0]["facets"] == ["INSTITUTION", "PLACE"]

    # Removing one axis leaves the other, and the exclusion with it.
    after = client.delete(f"/api/v1/taxonomy/tags/{tag.tag_id}/facets/{TagFacetType.PLACE.value}")
    assert after.status_code == HTTP_200_OK
    assert after.json()["facets"] == ["INSTITUTION"]
    assert client.get("/api/v1/taxonomy/tags/subject-exclusions").json() == ["prefeitura"]


def test_an_unknown_facet_type_is_refused(client: TestClient, api_uses_test_db, db_session: Session) -> None:
    """The axis is a closed vocabulary of two; a third one is not a stored value."""
    tag = _tag(db_session, "qualquer")
    db_session.flush()

    response = client.put(f"/api/v1/taxonomy/tags/{tag.tag_id}/facets/PLANET", json={})
    assert response.status_code in (400, 422)


# ==========================================
# THE CURATE PATH OF THE DOSSIER
# ==========================================


def test_the_dossier_verdict_is_durable_too(client: TestClient, api_uses_test_db, db_session: Session) -> None:
    """
    The same route serves the dossier's Assuntos tab, so the fix there is not a screen.

    The select that offers "sem categoria (não é assunto)" went through this route before the
    coupling existed, and its verdict was the one the next classifier run overwrote.
    """
    tag = _tag(db_session, "vista aerea")
    db_session.flush()

    assert client.patch(f"/api/v1/taxonomy/tags/{tag.tag_id}", json={"macro_category_id": None}).status_code == 200
    stored = client.get("/api/v1/taxonomy/tags/subject-exclusions")
    assert stored.status_code == HTTP_200_OK
    assert stored.json() == ["vista aerea"]

    # Un-banning from the exclusions screen re-opens the classifier for the term, and the tag goes
    # back to being an undecided orphan — the two reads agree on that too.
    removed = client.request("DELETE", "/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["vista aerea"]})
    assert removed.status_code == HTTP_200_OK
    assert _catalog(client, subject_state="PENDING", limit=25)["total"] == 1


def test_a_banned_term_registered_by_the_screen_reaches_the_catalogue(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """One definition of "not a subject": the row the exclusions screen writes is the state read."""
    tag = _tag(db_session, "capanema")
    db_session.flush()

    created = client.post("/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["capanema"]})
    assert created.status_code == HTTP_201_CREATED

    assert _catalog(client, subject_state="NOT_SUBJECT", limit=25)["total"] == 1
    assert _catalog(client, subject_state="PENDING", limit=25)["total"] == 0
    # The verdict silences the classifier: the tag is still in the collection, with its name.
    everything = _catalog(client, subject_state="ALL", limit=25)
    assert [row["name"] for row in everything["items"]] == [tag.name]
