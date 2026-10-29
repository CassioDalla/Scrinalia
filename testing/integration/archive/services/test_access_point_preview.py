"""The access-point preview reads the catalogue without writing, and the transfer agrees with it.

The form trusts two statements at once: what the summary says will happen, and what the transfer
does later. The last test pins the pair — a preview that promises another outcome is worse than no
preview, because the archivist decides on it.
"""

from sqlalchemy import select

from scrinalia.domains.archive.domain.access_points import AccessPointStatus
from scrinalia.domains.archive.models import ArchiveTag, DomainStopwords, DomainSynonyms
from scrinalia.domains.archive.models.enums import StopwordsScope
from scrinalia.domains.archive.repository.document_repo import DocumentRepository
from scrinalia.domains.archive.repository.tag_repo import TagRepository
from scrinalia.domains.archive.schemas import ArchiveTagDTO
from scrinalia.domains.archive.services.tag_service import TagService


def _service(db_session) -> TagService:
    return TagService(TagRepository(db_session), DocumentRepository(db_session))


def test_preview_access_points_reads_the_catalogue_without_writing(use_test_db, db_session):
    """The statuses are the transfer's vocabulary; the preview itself adds no row."""
    urbanismo = ArchiveTag(name="urbanismo")
    db_session.add(urbanismo)
    db_session.flush()
    db_session.add(DomainSynonyms(category="TAG", synonym_name="urbanismos", canonical_tag_id=urbanismo.tag_id))
    db_session.add_all(
        [
            DomainStopwords(word="obras", word_scope=StopwordsScope.TAG, source="HUMAN"),
            DomainStopwords(word="rio branco", word_scope=StopwordsScope.TAG, source="HUMAN"),
        ]
    )
    db_session.commit()

    service = _service(db_session)
    before = set(db_session.scalars(select(ArchiveTag.name)).all())
    result = service.preview_access_points("Urbanismo, urbanismos, obras, ab, rio  branco, Novo Termo, Novo Termo")
    after = set(db_session.scalars(select(ArchiveTag.name)).all())

    assert after == before
    assert [(item.input, item.status, item.name, item.tag_id) for item in result.items] == [
        ("Urbanismo", AccessPointStatus.EXISTING, "urbanismo", urbanismo.tag_id),
        ("urbanismos", AccessPointStatus.SYNONYM, "urbanismo", urbanismo.tag_id),
        ("obras", AccessPointStatus.STOPWORD, None, None),
        ("ab", AccessPointStatus.TOO_SHORT, None, None),
        ("rio  branco", AccessPointStatus.STOPWORD, None, None),
        ("Novo Termo", AccessPointStatus.NEW, "novo termo", None),
        ("Novo Termo", AccessPointStatus.DUPLICATE, None, None),
    ]


def test_the_preview_matches_what_process_worker_tags_links(use_test_db, db_session):
    """
    The two halves of the concept cannot drift.

    ``process_worker_tags`` is the write path the transfer uses; the preview is the read the form
    shows. Running the first on the names the second resolved must land on exactly the ids the
    second promised, and create exactly the new spellings it named.
    """
    urbanismo = ArchiveTag(name="urbanismo")
    db_session.add(urbanismo)
    db_session.flush()
    db_session.add(DomainSynonyms(category="TAG", synonym_name="urbanismos", canonical_tag_id=urbanismo.tag_id))
    db_session.commit()

    service = _service(db_session)
    preview = service.preview_access_points("Urbanismo, urbanismos, Novo Termo")

    linked_ids = service.process_worker_tags(
        [ArchiveTagDTO(name=item.name) for item in preview.items if item.name is not None]
    )
    db_session.commit()

    by_name = {tag.name: tag.tag_id for tag in db_session.scalars(select(ArchiveTag)).all()}

    assert set(linked_ids) == {urbanismo.tag_id, by_name["novo termo"]}
    assert by_name["novo termo"] != urbanismo.tag_id
    for item in preview.items:
        if item.status in (AccessPointStatus.EXISTING, AccessPointStatus.SYNONYM):
            assert item.tag_id == by_name[item.name]
