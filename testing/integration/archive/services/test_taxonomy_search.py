"""
The curator's two taxonomy reads that the dossier needs, and the write behind a reclassification.

The type-ahead reads exist because asking an archivist for the **id** of a tag is not a thing an
archivist knows, and the write exists because the drawer of a tag was, until now, only ever decided
by the classifier. Both are pinned here against the real database: the ordering and the wildcard
escaping of the searches, and the consequences of a human verdict on a tag — the drawer, the cleared
confidence and the mark in the ledger.
"""

import pytest
from sqlalchemy import select

from memoria_curitibana.domains.archive.exceptions import MacroCategoryNotFoundError, TagNotFoundError
from memoria_curitibana.domains.archive.models import (
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveMacroCategory,
    ArchiveTag,
)
from memoria_curitibana.domains.archive.models.associations import ArchiveDocumentEntity
from memoria_curitibana.domains.archive.repository.document_repo import DocumentRepository
from memoria_curitibana.domains.archive.repository.entity_repo import EntityRepository
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository
from memoria_curitibana.domains.archive.schemas import TagCurationCommand
from memoria_curitibana.domains.archive.services.entity_service import EntityService
from memoria_curitibana.domains.archive.services.tag_service import MIN_SEARCH_TERM, TagService
from memoria_curitibana.domains.archive.worker_stamp import CURATED_MACRO_CATEGORY


@pytest.fixture
def tag_service(db_session):
    return TagService(TagRepository(db_session), DocumentRepository(db_session))


@pytest.fixture
def entity_service(db_session):
    return EntityService(EntityRepository(db_session))


def _tag(db_session, generate_archive_doc, name: str, documents: int, category_id: int | None = None) -> ArchiveTag:
    """
    A tag carried by ``documents`` real descriptions.

    The links have a foreign key to ``archive_documents``, so the documents have to exist: a fake
    ``description_id`` here would fail on the constraint and hide what the test is about.
    """
    tag = ArchiveTag(name=name, macro_category_id=category_id)
    db_session.add(tag)
    db_session.flush()
    for index in range(documents):
        document = generate_archive_doc(
            description_id=f"{name.replace(' ', '-')}-{index}", original_title=f"Documento {name} {index}"
        )
        db_session.add(ArchiveDocumentTag(description_id=document.description_id, tag_id=tag.tag_id))
    db_session.flush()
    return tag


class TestTagSearch:
    def test_the_heaviest_match_comes_first(self, db_session, generate_archive_doc, tag_service):
        """
        Ordering is the feature, not a detail.

        The spelling the archivist wants is usually the one the collection actually used, and with
        thousands of variants that differ by a letter, an alphabetical list makes the box useless.
        """
        _tag(db_session, generate_archive_doc, "igreja", 5)
        _tag(db_session, generate_archive_doc, "igrejas", 7)
        _tag(db_session, generate_archive_doc, "igrejinha", 6)

        results = tag_service.search_tags("igrej", limit=10)

        assert [result.name for result in results] == ["igrejas", "igrejinha", "igreja"]
        assert [result.document_count for result in results] == [7, 6, 5]

    def test_the_drawer_travels_with_the_suggestion(self, db_session, generate_archive_doc, tag_service):
        """Without the drawer the curator picks a name with no context, which is how the wrong one wins."""
        category = ArchiveMacroCategory(name="Religião", description=None, is_active=True)
        db_session.add(category)
        db_session.flush()
        _tag(db_session, generate_archive_doc, "igrejas", 3, category_id=category.category_id)

        result = tag_service.search_tags("igrej", limit=5)[0]

        assert result.macro_category_name == "Religião"
        assert result.macro_category_id == category.category_id

    def test_a_wildcard_typed_by_a_person_is_a_character(self, db_session, generate_archive_doc, tag_service):
        """
        ``%`` and ``_`` in the box must be characters, not wildcards.

        Unescaped they match anything, so the archivist would see the whole catalogue for a typo
        and the query would stop using the trigram index. The terms here are two characters long
        because the search floor rejects single ones before the pattern is ever built — which is
        also why ``"%"`` on its own is not the test case.
        """
        _tag(db_session, generate_archive_doc, "igreja", 2)
        _tag(db_session, generate_archive_doc, "100% energia", 1)
        _tag(db_session, generate_archive_doc, "axb", 3)
        _tag(db_session, generate_archive_doc, "a_b", 1)

        # Unescaped, "0%" would match every name containing a zero and "a_b" every name with an "a"
        # followed by anything: the two assertions below are what separates the character from the
        # wildcard, and they are checked against tags that would otherwise win on document count.
        assert [result.name for result in tag_service.search_tags("0%", limit=10)] == ["100% energia"]
        assert [result.name for result in tag_service.search_tags("a_b", limit=10)] == ["a_b"]

    def test_a_shorter_term_than_the_floor_answers_nothing(self, db_session, generate_archive_doc, tag_service):
        _tag(db_session, generate_archive_doc, "igreja", 2)

        assert MIN_SEARCH_TERM == 2
        assert tag_service.search_tags("i", limit=10) == []
        assert tag_service.search_tags("%", limit=10) == []
        assert tag_service.search_tags("  ", limit=10) == []


class TestTagCuration:
    def test_a_human_verdict_moves_the_tag_and_clears_the_machine_score(
        self, db_session, generate_archive_doc, tag_service
    ):
        """
        The confidence belongs to the decision it was taken on.

        Leaving ``ai_confidence_score`` in place after a person decides would dress a human verdict
        in a machine's certainty — the same defect the confidence calibration work was about.
        """
        category = ArchiveMacroCategory(name="Religião", description=None, is_active=True)
        db_session.add(category)
        db_session.flush()
        tag = _tag(db_session, generate_archive_doc, "igrejas", 4)
        tag.ai_confidence_score = 0.71
        db_session.flush()

        result = tag_service.curate_tag_macro_category(
            tag.tag_id,
            TagCurationCommand(macro_category_id=category.category_id, changed_by="ana", note="não é transporte"),
        )

        stored = db_session.get(ArchiveTag, tag.tag_id)
        assert stored is not None
        assert stored.macro_category_id == category.category_id
        assert stored.ai_confidence_score is None
        assert result.human_classified is True
        assert result.macro_category_name == "Religião"

    def test_the_decision_is_marked_in_the_tag_ledger(self, db_session, generate_archive_doc, tag_service):
        """Tags have no revision table, so the stamp is the only trace the decision leaves."""
        category = ArchiveMacroCategory(name="Religião", description=None, is_active=True)
        db_session.add(category)
        db_session.flush()
        tag = _tag(db_session, generate_archive_doc, "igrejas", 1)

        tag_service.curate_tag_macro_category(
            tag.tag_id, TagCurationCommand(macro_category_id=category.category_id, changed_by="ana")
        )

        stored = db_session.get(ArchiveTag, tag.tag_id)
        assert stored is not None
        stamp = (stored.execution_log or {})[CURATED_MACRO_CATEGORY.key]
        assert stamp.startswith(f"{category.category_id}|ana|")

    def test_declaring_a_tag_no_subject_leaves_it_in_the_classifier_queue(
        self, db_session, generate_archive_doc, tag_service
    ):
        """
        ``None`` is a decision, not a missing value — and the queue the classifier reads is exactly
        the tags with no drawer, so declaring "not a subject" here puts the tag back in its reach.
        """
        category = ArchiveMacroCategory(name="Religião", description=None, is_active=True)
        db_session.add(category)
        db_session.flush()
        tag = _tag(db_session, generate_archive_doc, "vista aérea", 3, category_id=category.category_id)

        tag_service.curate_tag_macro_category(tag.tag_id, TagCurationCommand(macro_category_id=None))

        stored = db_session.get(ArchiveTag, tag.tag_id)
        assert stored is not None
        assert stored.macro_category_id is None
        pending = db_session.scalars(select(ArchiveTag.tag_id).where(ArchiveTag.macro_category_id.is_(None))).all()
        assert tag.tag_id in list(pending)

    def test_an_unknown_tag_is_a_not_found(self, tag_service):
        with pytest.raises(TagNotFoundError):
            tag_service.curate_tag_macro_category(999_999, TagCurationCommand(macro_category_id=None))

    def test_an_unknown_drawer_is_refused_before_the_write(self, db_session, generate_archive_doc, tag_service):
        """The vocabulary is a catalogue: a category that does not exist is not a drawer."""
        tag = _tag(db_session, generate_archive_doc, "igrejas", 1)

        with pytest.raises(MacroCategoryNotFoundError):
            tag_service.curate_tag_macro_category(tag.tag_id, TagCurationCommand(macro_category_id=999_999))

        stored = db_session.get(ArchiveTag, tag.tag_id)
        assert stored is not None
        assert stored.execution_log is None


class TestEntitySearch:
    def test_the_most_used_match_comes_first(self, db_session, generate_archive_doc, entity_service):
        db_session.add(ArchiveEntity(entity_id=1, name="Igreja do Rosário", entity_type="ORG"))
        db_session.add(ArchiveEntity(entity_id=2, name="Igreja Matriz", entity_type="LOC"))
        db_session.flush()
        for index in range(9):
            document = generate_archive_doc(description_id=f"matriz-{index}", original_title=f"Igreja Matriz {index}")
            db_session.add(ArchiveDocumentEntity(description_id=document.description_id, entity_id=2))
        for index in range(2):
            document = generate_archive_doc(description_id=f"rosario-{index}", original_title=f"Rosário {index}")
            db_session.add(ArchiveDocumentEntity(description_id=document.description_id, entity_id=1))
        db_session.flush()

        results = entity_service.search_entities("igreja", limit=5)

        assert [result.name for result in results] == ["Igreja Matriz", "Igreja do Rosário"]
        assert [result.total_usage for result in results] == [9, 2]
        assert results[0].entity_type == "LOC"

    def test_a_wildcard_typed_by_a_person_is_a_character(self, db_session, entity_service):
        db_session.add(ArchiveEntity(entity_id=3, name="Igreja 100%", entity_type="ORG"))
        db_session.add(ArchiveEntity(entity_id=5, name="Igreja Sao 0x", entity_type="LOC"))
        db_session.flush()

        # "0%" two characters in: only the name that literally carries "0%" may answer.
        assert [result.name for result in entity_service.search_entities("0%", limit=5)] == ["Igreja 100%"]

    def test_a_shorter_term_than_the_floor_answers_nothing(self, db_session, entity_service):
        db_session.add(ArchiveEntity(entity_id=4, name="Igreja Matriz", entity_type="LOC"))
        db_session.flush()

        assert entity_service.search_entities("i", limit=5) == []
        assert entity_service.search_entities("%", limit=5) == []
