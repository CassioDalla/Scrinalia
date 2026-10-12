"""The drawer's badge and the list it opens are the same number (issue #65).

``/assuntos/categorias`` shows each category with an "N descrições" badge and now expands into the
descriptions themselves, paged. Those are two different reads of **one** definition: the badge counts
distinct descriptions through the tag union (``TagRepository._macro_category_query``) and the list
counts the same rows through the ``EXISTS`` filter of the collection search
(``DocumentRepository._facet_filters``). A badge that promised 12 next to a list whose ``total`` said
9 is the read lying about the write — the defect the merge preview already has a test for.

Both are driven through the routes the screen calls, with the real repository: a mocked service would
pin the envelope and say nothing about the two queries agreeing.

The seed carries one description with **two** tags of the same drawer on purpose. Counting the join
instead of the documents answers 2 where the card promises 1, which is exactly the drift
``DISTINCT`` exists to prevent.
"""

from litestar.status_codes import HTTP_200_OK
from litestar.testing import TestClient
from sqlalchemy.orm import Session

from scrinalia.domains.archive.models import ArchiveDocumentTag, ArchiveMacroCategory, ArchiveTag


def _seed(db_session: Session) -> tuple[ArchiveMacroCategory, ArchiveTag, ArchiveTag, ArchiveTag]:
    """One drawer with two tags, one tag outside every drawer, and three descriptions."""
    category = ArchiveMacroCategory(name="Urbanismo", description=None, classifier_label=None, is_active=True)
    db_session.add(category)
    db_session.flush()

    first = ArchiveTag(name="urbanismo", macro_category_id=category.category_id)
    second = ArchiveTag(name="zoneamento", macro_category_id=category.category_id)
    outside = ArchiveTag(name="alvenaria", macro_category_id=None)
    db_session.add_all([first, second, outside])
    db_session.flush()
    return category, first, second, outside


def test_the_badge_and_the_list_total_are_the_same_number(
    client: TestClient, api_uses_test_db, db_session: Session, generate_archive_doc
) -> None:
    category, first, second, outside = _seed(db_session)

    heavy = generate_archive_doc(original_title="Duas tags da mesma categoria")
    light = generate_archive_doc(original_title="Uma tag da categoria")
    elsewhere = generate_archive_doc(original_title="Só a tag sem categoria")
    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=heavy.description_id, tag_id=first.tag_id),
            ArchiveDocumentTag(description_id=heavy.description_id, tag_id=second.tag_id),
            ArchiveDocumentTag(description_id=light.description_id, tag_id=first.tag_id),
            ArchiveDocumentTag(description_id=elsewhere.description_id, tag_id=outside.tag_id),
        ]
    )
    db_session.flush()

    catalog = client.get("/api/v1/taxonomy/macro-categories")
    assert catalog.status_code == HTTP_200_OK
    badge = next(row for row in catalog.json() if row["category_id"] == category.category_id)
    # Two descriptions, not three links: the drawer's weight is documents, not spellings.
    assert badge["document_count"] == 2

    listing = client.get(f"/api/v1/documents?macro_category_id={category.category_id}&limit=10&offset=0")
    assert listing.status_code == HTTP_200_OK
    body = listing.json()
    assert body["total"] == badge["document_count"]
    assert {item["description_id"] for item in body["items"]} == {heavy.description_id, light.description_id}

    # The total is the count of the result set, not of the page: it must not move with the offset.
    page = client.get(f"/api/v1/documents?macro_category_id={category.category_id}&limit=1&offset=1").json()
    assert page["total"] == badge["document_count"]
    assert len(page["items"]) == 1


def test_a_drawer_with_no_descriptions_promises_zero_and_lists_none(
    client: TestClient, api_uses_test_db, db_session: Session
) -> None:
    """The retired drawer: the card says 0 and the expansion answers an empty page, not an error."""
    category = ArchiveMacroCategory(name="Retirada", description=None, classifier_label=None, is_active=False)
    db_session.add(category)
    db_session.flush()

    badge = next(
        row
        for row in client.get("/api/v1/taxonomy/macro-categories").json()
        if row["category_id"] == category.category_id
    )
    assert badge["document_count"] == 0

    listing = client.get(f"/api/v1/documents?macro_category_id={category.category_id}&limit=10&offset=0").json()
    assert listing["total"] == 0
    assert listing["items"] == []
