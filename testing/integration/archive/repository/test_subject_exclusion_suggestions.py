"""
The "not a subject" suggestions: the guard's verdicts made legible.

The measurement is the argument for this route existing at all. ``is_subject_candidate`` already
refuses 1.489 of the 8.155 real tags inside ``worker_macro_category``, and nothing ever recorded it:
``source='RULE'`` sat in the schema's check constraint with no writer. Meanwhile the signals that
*could* have been used to guess the semantic half lie — by document count the top of the orphans is
``igrejas`` (2.474, a real subject missing a drawer) and by low confidence it is ``madeira`` (0.30),
also a real subject.

So the route proposes exactly what the guard refuses, carries the evidence beside each candidate, and
proposes nothing else.
"""

from sqlalchemy import select

from memoria_curitibana.domains.archive.models import (
    ArchiveDocumentTag,
    ArchiveEntity,
    ArchiveTag,
    DomainSubjectExclusion,
)
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository


def _tag_with_documents(db_session, name: str, documents: list[str]) -> ArchiveTag:
    tag = ArchiveTag(name=name)
    db_session.add(tag)
    db_session.flush()
    for description_id in documents:
        db_session.add(ArchiveDocumentTag(description_id=description_id, tag_id=tag.tag_id))
    db_session.flush()
    return tag


def test_it_proposes_what_the_guard_refuses_with_the_weight_beside_it(use_test_db, db_session, generate_archive_doc):
    """
    A candidate is the guard's verdict plus the evidence the archivist decides with.

    ``document_count`` is the weight at stake and it is the sort key: the terms that move the
    collection come first, not the alphabet.
    """
    repo = TagRepository(db_session)
    heavy = generate_archive_doc(description_id="s1", original_title="A")
    _tag_with_documents(db_session, "local não identificado", ["s1"])
    _tag_with_documents(db_session, "1924", [heavy.description_id])
    _tag_with_documents(db_session, "igrejas", [heavy.description_id])  # a real subject: no signal

    response = repo.find_subject_exclusion_candidates()

    terms = [item.term for item in response.items]
    assert "igrejas" not in terms, "um assunto real não pode virar sugestão de não-assunto"
    assert set(terms) == {"local não identificado", "1924"}
    assert response.candidate_count == 2
    assert response.by_signal == {"PLACEHOLDER": 1, "YEAR": 1}

    by_term = {item.term: item for item in response.items}
    assert by_term["1924"].signal == "YEAR"
    assert by_term["1924"].document_count == 1
    assert by_term["local não identificado"].signal == "PLACEHOLDER"


def test_the_evidence_says_where_the_term_goes_and_what_else_it_is(use_test_db, db_session, generate_archive_doc):
    """
    "Not a subject" is not "goes nowhere", and the screen has to be able to say so.

    A street is refused by the guard **and** claimed by the PLACE facet, so excluding it from the
    subject axis does not discard it. And a spelling that also exists as a named entity is the
    collision screen's business, not this one's.
    """
    repo = TagRepository(db_session)
    document = generate_archive_doc(description_id="s2", original_title="A")
    _tag_with_documents(db_session, "rua xv de novembro", [document.description_id])
    _tag_with_documents(db_session, "joel rocha", [document.description_id])
    db_session.add(ArchiveEntity(name="Joel Rocha", entity_type="PER"))
    db_session.flush()

    response = repo.find_subject_exclusion_candidates()
    by_term = {item.term: item for item in response.items}

    street = by_term["rua xv de novembro"]
    assert street.is_place_term is True, "a rua vai para a faceta Lugar"
    assert street.also_an_entity is False
    assert response.place_count == 1

    person = by_term["joel rocha"]
    assert person.signal == "PERSON"
    assert person.also_an_entity is True, "a mesma grafia vive no eixo de entidades"
    assert person.word_count == 2


def test_a_recorded_decision_is_not_proposed_again(use_test_db, db_session, generate_archive_doc):
    """The catalogue is the durable decision, so an excluded term leaves the candidate list."""
    repo = TagRepository(db_session)
    document = generate_archive_doc(description_id="s3", original_title="A")
    _tag_with_documents(db_session, "1924", [document.description_id])
    repo.add_subject_exclusions(["1924"], source="RULE", reason="ano isolado")
    db_session.flush()

    response = repo.find_subject_exclusion_candidates()

    assert response.items == []
    assert response.candidate_count == 0
    assert response.already_excluded_count == 1

    # Asked for, the recorded ones come back marked, so the screen can show the whole class — and
    # the signal stays: it is the guard's reason, which is worth knowing even after the decision.
    with_recorded = repo.find_subject_exclusion_candidates(include_excluded=True)
    assert [(item.term, item.already_excluded, item.signal) for item in with_recorded.items] == [("1924", True, "YEAR")]

    # A term recorded by hand has no shape to report, and says so instead of inventing one. The tag
    # has to exist: the route lists the vocabulary, so an exclusion whose tag is gone (the purge
    # deletes tags and keeps the decision) is not something it can weigh.
    _tag_with_documents(db_session, "vista aérea", [])
    repo.add_subject_exclusions(["vista aérea"], source="HUMAN", reason="ponto de vista")
    db_session.flush()
    recorded = repo.find_subject_exclusion_candidates(include_excluded=True)
    assert [(item.term, item.signal) for item in recorded.items] == [
        ("1924", "YEAR"),
        ("vista aérea", "RECORDED"),
    ]


def test_the_write_records_who_decided(use_test_db, db_session, generate_archive_doc):
    """
    ``source`` is what tells a shape from a judgement, and nothing ever wrote ``RULE`` before.

    A term the guard refused and the archivist confirmed is a different statement from a term the
    archivist typed — both are reversible, and the column is what keeps them apart.
    """
    repo = TagRepository(db_session)

    assert repo.add_subject_exclusions(["1924"], source="RULE", reason="ano isolado") == 1
    assert repo.add_subject_exclusions(["vista aérea"], source="HUMAN", reason="ponto de vista") == 1
    db_session.flush()

    sources = dict(db_session.execute(select(DomainSubjectExclusion.term, DomainSubjectExclusion.source)).all())
    assert sources == {"1924": "RULE", "vista aérea": "HUMAN"}


def test_excluding_does_not_delete_the_tag_or_its_links(use_test_db, db_session, generate_archive_doc):
    """
    The subject axis is silenced, not the term: it stays a tag, linked and reachable by search.

    This is the difference from the NER exclusion's retroactive purge, and the screen states it.
    """
    repo = TagRepository(db_session)
    document = generate_archive_doc(description_id="s4", original_title="A")
    tag = _tag_with_documents(db_session, "local não identificado", [document.description_id])

    repo.add_subject_exclusions(["local não identificado"], source="RULE")
    db_session.flush()

    assert db_session.get(ArchiveTag, tag.tag_id) is not None
    links = db_session.scalars(
        select(ArchiveDocumentTag.description_id).where(ArchiveDocumentTag.tag_id == tag.tag_id)
    ).all()
    assert list(links) == ["s4"]


def test_the_page_does_not_change_the_totals(use_test_db, db_session, generate_archive_doc):
    """The counts are over the whole candidate set, because the screen shows them beside the list."""
    repo = TagRepository(db_session)
    for year in ("1910", "1924", "2019"):
        _tag_with_documents(db_session, year, [])

    page = repo.find_subject_exclusion_candidates(limit=1, offset=0)

    assert page.total == 3
    assert page.candidate_count == 3
    assert len(page.items) == 1
    assert page.by_signal == {"YEAR": 3}


def test_it_does_not_propose_the_semantic_half(use_test_db, db_session, generate_archive_doc):
    """
    The three measured non-subjects no rule reaches must not be proposed.

    ``pessoas`` (166 documents), ``vista aérea`` (89) and ``capanema`` (91) are the hand-labelled
    cases the guard was measured to miss — one of four. Proposing them automatically would be a wrong
    verdict with a confident tone, which is exactly what the model does and why this route is
    deterministic.
    """
    repo = TagRepository(db_session)
    for term in ("pessoas", "vista aérea", "capanema"):
        _tag_with_documents(db_session, term, [])

    response = repo.find_subject_exclusion_candidates()

    assert response.items == []
    assert response.candidate_count == 0
