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
from sqlalchemy import select
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import (
    AnomalyType,
    ArchiveAIReviewQueue,
    ArchiveMacroCategory,
    ArchiveReviewStatus,
    ArchiveTag,
    DomainStopwords,
    DomainSubjectExclusion,
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

    pending = _catalog(client, subject_state="PENDING", limit=25)
    assert pending["total"] == _inbox(client)["orphan_subject_tags"] == 2
    assert {row["name"] for row in pending["items"]} == {"alvenaria", "zoneamento"}

    # And the slice showed the whole catalogue, not a top-N: the decided tags are still listed,
    # each one explaining its own state.
    everything = _catalog(client, subject_state="ALL", limit=25)
    assert everything["total"] == 4
    by_name = {row["name"]: row for row in everything["items"]}
    assert by_name["urbanismo"]["macro_category_name"] == "Urbanismo"
    assert by_name["cidade"]["subject_excluded"] is True


def test_the_decision_states_partition_the_catalogue(client: TestClient, api_uses_test_db, db_session: Session) -> None:
    """A tag is in exactly one of the two undecided/decided slices, plus the drawers."""
    category = _category(db_session)
    _tag(db_session, "com-categoria", macro_category_id=category.category_id)
    _tag(db_session, "pendente-1")
    _tag(db_session, "pendente-2")
    db_session.add(DomainSubjectExclusion(term="nao-assunto", source="HUMAN"))
    _tag(db_session, "nao-assunto")
    db_session.flush()

    total = _catalog(client, subject_state="ALL", limit=25)["total"]
    slices = {state: _catalog(client, subject_state=state, limit=25)["total"] for state in ("PENDING", "NOT_SUBJECT")}

    assert slices == {"PENDING": 2, "NOT_SUBJECT": 1}
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

    This door and the "not a subject" screen are one statement, not two: both ban the spelling at
    ``TAG`` scope, or the term keeps coming back through whichever door was not used (ADR 0013).
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
    ban = db_session.scalars(select(DomainStopwords).where(DomainStopwords.word == "pessoas")).one()
    assert (ban.word_scope.value, ban.source) == ("TAG", "EXCLUSION")

    # Out of the queue, still in the collection: the total of the catalogue does not move.
    assert _catalog(client, subject_state="PENDING", limit=25)["total"] == 0
    assert _catalog(client, subject_state="NOT_SUBJECT", limit=25)["total"] == 1
    assert _catalog(client, subject_state="ALL", limit=25)["total"] == 1
    assert _inbox(client)["orphan_subject_tags"] == 0


def test_filing_a_tag_takes_it_off_the_non_subject_axis(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """A tag in a drawer is not also a term the classifier must skip."""
    category = _category(db_session)
    tag = _tag(db_session, "centro")
    db_session.add(DomainSubjectExclusion(term="centro", source="HUMAN"))
    db_session.flush()

    response = client.patch(f"/api/v1/taxonomy/tags/{tag.tag_id}", json={"macro_category_id": category.category_id})
    assert response.status_code == HTTP_200_OK
    assert response.json()["subject_excluded"] is False

    everything = _catalog(client, subject_state="ALL", limit=25)
    row = next(item for item in everything["items"] if item["tag_id"] == tag.tag_id)
    assert row["macro_category_id"] == category.category_id
    assert row["subject_excluded"] is False
    assert client.get("/api/v1/taxonomy/tags/subject-exclusions").json() == []


def test_the_exclusion_refuses_a_term_whose_tag_is_already_in_a_drawer(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """
    Issue #83, option C: the write that settles a *tag* is the catalogue's, not this one's.

    A drawer is a human verdict, and a statement about a *term* must not un-file it. The route
    answers the refusal and names the tag and its drawer, so the screen can send the archivist to the
    catalogue instead of silently doing the opposite of what they asked.
    """
    category = _category(db_session)
    tag = _tag(db_session, "centro", macro_category_id=category.category_id)
    db_session.flush()

    refused = client.post("/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["centro"]})
    assert refused.status_code == HTTP_201_CREATED, refused.text
    body = refused.json()
    assert body["code"] == "SUBJECT_EXCLUSIONS_BLOCKED"
    assert body["created"] == 0
    assert body["banned"] == 0
    assert body["blocked"] == [
        {
            "term": "centro",
            "signal": None,
            "is_place_term": False,
            "also_an_entity": False,
            "document_count": 0,
            "tag_id": tag.tag_id,
            "macro_category_id": category.category_id,
            "macro_category_name": "Urbanismo",
            "already_excluded": False,
            "already_banned": False,
        }
    ]

    # Nothing moved: the drawer stands, no exclusion was recorded and no spelling was banned.
    assert client.get("/api/v1/taxonomy/tags/subject-exclusions").json() == []
    row = next(
        item for item in _catalog(client, subject_state="ALL", limit=25)["items"] if item["tag_id"] == tag.tag_id
    )
    assert row["macro_category_id"] == category.category_id
    assert row["subject_excluded"] is False
    assert db_session.scalars(select(DomainStopwords)).all() == []


def test_a_partial_exclusion_reports_both_numbers(client: TestClient, api_uses_test_db, db_session: Session) -> None:
    """One blocked term must not hide the term the write did record."""
    category = _category(db_session)
    _tag(db_session, "centro", macro_category_id=category.category_id)
    _tag(db_session, "vista aerea")
    db_session.flush()

    response = client.post("/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["centro", "vista aerea"]})
    assert response.status_code == HTTP_201_CREATED, response.text
    body = response.json()
    assert body["code"] == "SUBJECT_EXCLUSIONS_PARTIAL"
    assert body["created"] == 1
    assert body["banned"] == 1
    assert [item["term"] for item in body["blocked"]] == ["centro"]
    assert client.get("/api/v1/taxonomy/tags/subject-exclusions").json() == ["vista aerea"]


def test_the_preview_says_what_the_write_would_do_without_writing(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """The dry run of the write: the same plan the write consumes, so it cannot promise another number."""
    category = _category(db_session)
    _tag(db_session, "centro", macro_category_id=category.category_id)
    _tag(db_session, "capanema")
    db_session.flush()

    preview = client.post("/api/v1/taxonomy/tags/subject-exclusions/preview", json={"words": ["centro", "capanema"]})
    assert preview.status_code == HTTP_200_OK, preview.text
    body = preview.json()
    assert [item["term"] for item in body["applicable"]] == ["capanema"]
    assert [item["term"] for item in body["blocked"]] == ["centro"]
    assert body["blocked"][0]["macro_category_name"] == "Urbanismo"

    # A preview writes nothing.
    assert client.get("/api/v1/taxonomy/tags/subject-exclusions").json() == []
    assert db_session.scalars(select(DomainStopwords)).all() == []


def test_confirming_not_a_subject_bans_the_spelling_at_tag_scope(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """
    Issue #84: the exclusion silences the classifier **and** stops the spelling coming back.

    The scope is the safety: a ``TAG`` ban is read by ``extract_and_clean_tags`` and never by the
    NER, whose blacklist reads ``ENTITY``/``ALL`` only. So the tag stops being recreated while the
    name keeps being extracted from the document text.
    """
    _tag(db_session, "capanema")
    db_session.flush()

    created = client.post("/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["capanema"]})
    assert created.status_code == HTTP_201_CREATED
    body = created.json()
    assert body["code"] == "SUBJECT_EXCLUSIONS_ADDED"
    assert body["created"] == 1
    assert body["banned"] == 1

    ban = db_session.scalars(select(DomainStopwords).where(DomainStopwords.word == "capanema")).one()
    assert ban.word_scope.value == "TAG"
    assert ban.source == "EXCLUSION"
    exclusion = db_session.scalars(select(DomainSubjectExclusion)).one()
    assert exclusion.ban_created is True

    # The restore lifts both halves this write planted: the term is classified again and can become
    # a tag again. What it does not lift is a ban somebody else owns — the next test pins that.
    removed = client.request("DELETE", "/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["capanema"]})
    assert removed.status_code == HTTP_200_OK
    assert removed.json()["removed"] == 1
    assert removed.json()["unbanned"] == 1
    assert db_session.scalars(select(DomainStopwords)).all() == []


def test_the_restore_leaves_a_ban_a_person_owns(client: TestClient, api_uses_test_db, db_session: Session) -> None:
    """
    The ban has two writers, so the undo has to know which one planted it.

    A person bans ``capanema`` on the Stopwords screen (``source=HUMAN``); confirming it as
    not-a-subject finds the ban already there and records ``ban_created=False``; restoring the
    exclusion must leave the person's ban standing.
    """
    _tag(db_session, "capanema")
    db_session.flush()

    banned = client.post("/api/v1/taxonomy/tags/stopwords", json={"words": ["capanema"], "scope": "TAG"})
    assert banned.status_code == HTTP_201_CREATED, banned.text

    created = client.post("/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["capanema"]})
    assert created.status_code == HTTP_201_CREATED
    assert created.json()["banned"] == 0
    assert db_session.scalars(select(DomainSubjectExclusion)).one().ban_created is False

    removed = client.request("DELETE", "/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["capanema"]})
    assert removed.status_code == HTTP_200_OK
    assert removed.json()["unbanned"] == 0
    ban = db_session.scalars(select(DomainStopwords).where(DomainStopwords.word == "capanema")).one()
    assert ban.source == "HUMAN"


def test_an_entity_scoped_veto_is_widened_and_never_narrowed(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """
    Coupling must not blind the NER: an ``ENTITY`` veto becomes ``ALL``, it is never moved to ``TAG``.

    ``domain_stopwords.word`` is unique and ``save_stopwords`` *moves* the scope on conflict, so
    writing the ban through that path would silently un-veto the extraction axis. ``ensure_tag_ban``
    is the write that widens.
    """
    tag = _tag(db_session, "josé pedro")
    db_session.add(DomainStopwords(word="josé pedro", word_scope="ENTITY", source="HUMAN"))
    db_session.flush()

    created = client.post("/api/v1/taxonomy/tags/subject-exclusions", json={"words": [tag.name]})
    assert created.status_code == HTTP_201_CREATED

    ban = db_session.scalars(select(DomainStopwords).where(DomainStopwords.word == "josé pedro")).one()
    assert ban.word_scope.value == "ALL", "the NER veto has to survive the coupling"
    assert ban.source == "HUMAN", "the origin of the ban is whoever planted it"


def test_the_purge_preview_names_the_origin_of_each_ban(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """The purge has to say which terms were banned with the archive in mind and which were typed."""
    _tag(db_session, "capanema")
    typed = _tag(db_session, "rascunho")
    db_session.flush()

    assert client.post("/api/v1/taxonomy/tags/subject-exclusions", json={"words": ["capanema"]}).status_code == 201
    assert (
        client.post("/api/v1/taxonomy/tags/stopwords", json={"words": [typed.name], "scope": "TAG"}).status_code == 201
    )

    preview = client.post("/api/v1/taxonomy/tags/stopwords/purge/preview")
    assert preview.status_code == HTTP_200_OK
    by_name = {tag["name"]: tag for tag in preview.json()["tags"]}
    assert by_name["capanema"]["source"] == "EXCLUSION"
    assert by_name["rascunho"]["source"] == "HUMAN"


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


def test_a_negative_offset_is_clamped_instead_of_failing(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """
    PostgreSQL refuses ``OFFSET -1``, and the route used to answer 500 for it.

    The clamp lives in the service and not only on the query parameter: the service is the boundary
    every caller goes through, and the next caller would have had to remember.
    """
    _tag(db_session, "pendente")
    db_session.flush()

    response = client.get("/api/v1/taxonomy/tags/catalog?subject_state=PENDING&limit=5&offset=-1")

    assert response.status_code == HTTP_200_OK, response.text
    assert response.json()["offset"] == 0
    assert response.json()["total"] == 1
