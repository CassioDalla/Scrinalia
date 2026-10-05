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
    ArchiveTaxonomyMergeLog,
)
from memoria_curitibana.domains.archive.models.associations import ArchiveDocumentEntity
from memoria_curitibana.domains.archive.models.enums import StopwordsScope
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


class TestDrawerWeight:
    def test_a_drawer_counts_descriptions_not_links(self, db_session, generate_archive_doc, tag_service):
        """
        A document with three tags in the same drawer is **one** document in that drawer.

        Counting links would make the weight of a drawer depend on how many spellings its documents
        happen to carry — ``alvenaria`` and ``alvenarias`` would double the same house — and the
        screen exists to show how much of the collection each drawer holds.
        """
        category = ArchiveMacroCategory(name="Urbanismo e Arquitetura", description=None, is_active=True)
        db_session.add(category)
        db_session.flush()
        _tag(db_session, generate_archive_doc, "alvenaria", 2, category_id=category.category_id)

        # One document, two tags of the same drawer: it must count once.
        shared = generate_archive_doc(description_id="shared-1", original_title="Mesma casa")
        for name in ("casa", "residencial"):
            tag = ArchiveTag(name=name, macro_category_id=category.category_id)
            db_session.add(tag)
            db_session.flush()
            db_session.add(ArchiveDocumentTag(description_id=shared.description_id, tag_id=tag.tag_id))
        db_session.flush()

        drawer = next(item for item in tag_service.list_macro_categories() if item.category_id == category.category_id)

        # Two documents carry "alvenaria" and one carries the other two: three descriptions, four links.
        assert drawer.document_count == 3

    def test_an_edited_drawer_keeps_its_weight(self, db_session, generate_archive_doc, tag_service):
        """The response of an edit is read back through the counted view, not from the ORM row."""
        category = ArchiveMacroCategory(name="Religião", description=None, is_active=True)
        db_session.add(category)
        db_session.flush()
        _tag(db_session, generate_archive_doc, "igrejas", 4, category_id=category.category_id)

        from memoria_curitibana.domains.archive.schemas import UpdateMacroCategoryCommand

        updated = tag_service.update_macro_category(
            category.category_id, UpdateMacroCategoryCommand(classifier_label="religião, fé")
        )

        assert updated.classifier_label == "religião, fé"
        assert updated.document_count == 4


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


class TestStopwords:
    """
    The banned-term catalog and the one destructive write that has no undo.

    The scope is the whole point of these tests: ``TAG`` feeds the subject purge while ``ENTITY``
    keeps a term out of the NER extraction, and the repository reads only ``TAG``/``ALL`` on purpose.
    Collapsing the two would make a veto on one axis delete the other.
    """

    def test_terms_are_listed_with_the_axis_they_were_banned_from(self, tag_service):
        tag_service.save_new_stopwords(["pessoas", "vista aérea"], StopwordsScope.TAG)
        tag_service.save_new_stopwords(["iptu"], StopwordsScope.ENTITY)

        everything = tag_service.list_stopwords()
        subject_only = tag_service.list_stopwords(StopwordsScope.TAG)

        assert {(item.word, str(item.scope)) for item in everything} == {
            ("pessoas", "TAG"),
            ("vista aérea", "TAG"),
            ("iptu", "ENTITY"),
        }
        assert [item.word for item in subject_only] == ["pessoas", "vista aérea"]

    def test_re_banning_a_term_moves_its_axis(self, tag_service):
        """
        A word has **one** scope — ``domain_stopwords.word`` is unique — so re-banning moves it.

        The alternative (ignoring the second ban) would leave the screen showing the axis the
        archivist just changed away from, and the entity/subject distinction is exactly what makes
        that dangerous: a term would look banned from the NER while it is banned from the subjects.
        """
        tag_service.save_new_stopwords(["iptu"], StopwordsScope.TAG)
        tag_service.save_new_stopwords(["iptu"], StopwordsScope.ENTITY)

        listed = tag_service.list_stopwords()

        assert [(item.word, str(item.scope)) for item in listed] == [("iptu", "ENTITY")]

    def test_un_banning_without_a_scope_removes_the_word_whatever_axis_it_was_on(self, tag_service):
        """Un-banning is the only way back from a purge decision, so it cannot depend on knowing the axis."""
        tag_service.save_new_stopwords(["pessoas"], StopwordsScope.ENTITY)

        assert tag_service.remove_stopwords(["pessoas"]) == 1
        assert tag_service.list_stopwords() == []

    def test_un_banning_one_axis_leaves_terms_of_the_other_alone(self, tag_service):
        tag_service.save_new_stopwords(["pessoas"], StopwordsScope.TAG)
        tag_service.save_new_stopwords(["iptu"], StopwordsScope.ENTITY)

        assert tag_service.remove_stopwords(["pessoas"], StopwordsScope.ENTITY) == 0
        assert [item.word for item in tag_service.list_stopwords()] == ["iptu", "pessoas"]

    def test_the_preview_shows_what_the_purge_would_delete(self, db_session, generate_archive_doc, tag_service):
        """
        The purge is the only destructive taxonomy write with no ledger, so the screen shows the
        loss first: the name, how many descriptions carry it and which drawer dies with it.
        """
        category = ArchiveMacroCategory(name="Assistência e Questões Sociais", description=None, is_active=True)
        db_session.add(category)
        db_session.flush()
        _tag(db_session, generate_archive_doc, "pessoas", 3, category_id=category.category_id)
        _tag(db_session, generate_archive_doc, "vista aérea", 2)
        tag_service.save_new_stopwords(["pessoas"], StopwordsScope.TAG)

        preview = tag_service.preview_stopword_purge()

        assert preview.stopwords == ["pessoas"]
        assert [tag.name for tag in preview.tags] == ["pessoas"]
        assert preview.tags[0].document_count == 3
        assert preview.tags[0].macro_category_name == "Assistência e Questões Sociais"
        assert preview.total_documents == 3
        # Announced, never silently reversible: there is no ledger behind this write.
        assert preview.reversible is False

    def test_an_entity_scoped_ban_never_reaches_the_subject_purge(self, db_session, generate_archive_doc, tag_service):
        """
        The invariant ``AGENTS.md`` calls out: a NER veto must not delete a tag.

        ``iptu`` banned on the entity axis keeps the model from extracting it as a name; it says
        nothing about the subject axis, where the same spelling may be a legitimate tag. Reading the
        entity ban in the purge would delete a tag the curator deliberately kept.
        """
        _tag(db_session, generate_archive_doc, "iptu", 4)
        tag_service.save_new_stopwords(["iptu"], StopwordsScope.ENTITY)

        preview = tag_service.preview_stopword_purge()
        deleted = tag_service.purge_stopwords()

        assert preview.stopwords == []
        assert preview.tags == []
        assert deleted == 0
        assert db_session.scalars(select(ArchiveTag).where(ArchiveTag.name == "iptu")).one() is not None

    def test_the_purge_deletes_the_tag_and_its_links_and_is_not_reversible(
        self, db_session, generate_archive_doc, tag_service
    ):
        tag = _tag(db_session, generate_archive_doc, "pessoas", 3)
        tag_service.save_new_stopwords(["pessoas"], StopwordsScope.TAG)

        deleted = tag_service.purge_stopwords()

        assert deleted == 1
        assert db_session.get(ArchiveTag, tag.tag_id) is None
        links = db_session.scalars(select(ArchiveDocumentTag).where(ArchiveDocumentTag.tag_id == tag.tag_id)).all()
        assert links == []
        # The contrast that the screen has to state: the merge keeps a ledger, this does not.
        assert db_session.scalars(select(ArchiveTaxonomyMergeLog)).all() == []
