from unittest.mock import patch

from sqlalchemy import select

from scrinalia.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveEntity,
    ArchiveReviewStatus,
    ArchiveTag,
    DomainNerExclusion,
    DomainStopwords,
)
from scrinalia.domains.archive.repository.document_repo import DocumentRepository
from scrinalia.domains.archive.repository.entity_repo import EntityRepository
from scrinalia.domains.archive.schemas.entity_schema import ArchiveEntityDTO
from scrinalia.domains.archive.workers.worker_ner import execute, load_entity_blacklist


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_skips_human_approved(
    mock_get_engine,
    db_session,
    generate_archive_doc,
):
    """Governance: a HUMAN_APPROVED document must be shielded from AI re-processing."""
    generate_archive_doc(
        description_id="doc_human",
        original_title="Documento revisado pelo arquivista",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )

    execute(db=db_session)

    # The AI must never even be consulted for a human-approved document.
    mock_get_engine.return_value.extract.assert_not_called()

    db_session.expire_all()
    approved = db_session.get(ArchiveDocument, "doc_human")
    assert approved.execution_log is None or "worker_ner_v2" not in approved.execution_log


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_real_database(
    mock_get_engine,
    db_session,  # Your injected PostgreSQL session!
    generate_archive_doc,  # Your document factory
):
    """Integration: Tests the real SQL for inserting Entities and manipulating the JSONB field."""
    ner_engine_mock = mock_get_engine.return_value

    # 1. AI MOCK: We simulate the AI finding 2 entities in the text
    ner_engine_mock.extract.return_value = [
        [
            ArchiveEntityDTO(name="David Carneiro", entity_type="PER"),
            ArchiveEntityDTO(name="Curitiba", entity_type="LOC"),
        ]
    ]

    # 2. SETUP: We insert a real document into PostgreSQL
    real_doc = generate_archive_doc(
        description_id="doc_ner_1",
        original_title="Relatório Anual",
        scope_content="Documento emitido na cidade de Curitiba por David Carneiro.",
    )
    db_session.add(real_doc)
    db_session.commit()

    # 3. ACTION: The Worker runs using the real session (we do NOT mock the repository!)
    execute(db=db_session)

    # 4. CHECKS: Document updated
    db_session.expire_all()  # Clears the cache to force a fresh read from the database
    updated_doc = db_session.get(ArchiveDocument, "doc_ner_1")

    # Checks whether the JSONB was written perfectly to disk
    assert updated_doc.execution_log is not None
    assert updated_doc.execution_log["worker_ner_v2"] == "DONE"

    # Confirms the correct sending of the concatenated text to the AI
    args, _ = ner_engine_mock.extract.call_args
    assert args[0] == ["Relatório Anual. Documento emitido na cidade de Curitiba por David Carneiro."]

    # 5. CHECKS: Did the database receive the correct inserts?
    db_entities = db_session.scalars(select(ArchiveEntity)).all()
    assert len(db_entities) == 2
    names = {e.name for e in db_entities}

    # Entity names are normalized to lowercase on persistence.
    assert "david carneiro" in names
    assert "curitiba" in names

    # Checks whether the associative table (N:N) was populated
    links = db_session.scalars(select(ArchiveDocumentEntity)).all()
    assert len(links) == 2


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_ignores_already_processed_documents(mock_get_engine, db_session, generate_archive_doc):
    """Integration: Validates whether the SQLAlchemy WHERE query respects the JSONB negation in PostgreSQL."""
    # We insert a document into the real database that ALREADY HAS the stamp
    old_doc = generate_archive_doc(
        original_title="Documento Antigo", execution_log={"worker_ner_v2": "DONE", "algum_outro_worker": "ERROR"}
    )
    db_session.add(old_doc)
    db_session.commit()

    # Run the orchestrator
    execute(db=db_session)

    # Checks whether the AI was completely ignored, since the database query must have returned empty
    mock_get_engine.return_value.extract.assert_not_called()


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_processes_multiple_batches(mock_get_engine, db_session, generate_archive_doc):
    """Integration: Validates whether the 'while True' advances correctly through the limit pages in the DB."""
    ner_engine_mock = mock_get_engine.return_value

    # We create 3 documents in the database
    docs = [
        generate_archive_doc(description_id="doc-1", original_title="Texto 1"),
        generate_archive_doc(description_id="doc-2", original_title="Texto 2"),
        generate_archive_doc(description_id="doc-3", original_title="Texto 3"),
    ]
    db_session.add_all(docs)
    db_session.commit()

    # The AI Mock must return empty entity lists consistent with the batches.
    # Batch 1 has 2 documents (returns [[], []]). Batch 2 has 1 document (returns [[]]).
    ner_engine_mock.extract.side_effect = [[[], []], [[]]]

    # We run forcing a tiny batch_size of 2
    # This will force the worker to take 2 turns around the while loop
    execute(db=db_session, db_batch_size=2)

    db_session.expire_all()

    # All 3 documents must have the DONE stamp saved in the database
    assert db_session.get(ArchiveDocument, "doc-1").execution_log["worker_ner_v2"] == "DONE"
    assert db_session.get(ArchiveDocument, "doc-2").execution_log["worker_ner_v2"] == "DONE"
    assert db_session.get(ArchiveDocument, "doc-3").execution_log["worker_ner_v2"] == "DONE"

    # The AI inference (batch extract) must have been called exactly 2 times
    assert ner_engine_mock.extract.call_count == 2


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_integration_ignores_fully_null_rows(mock_get_engine, db_session, generate_archive_doc):
    """Integration: Validates the assembly of the dynamic or_() in SQLAlchemy. Docs without texts do not enter the queue."""
    # Document where the fields we asked to extract are explicitly None
    ghost_doc = generate_archive_doc(
        description_id="doc_fantasma",
        original_title="Titulo teste doc",
        admin_bio_history=None,
        provenance=None,
        scope_content=None,
    )
    db_session.add(ghost_doc)
    db_session.commit()

    # We run the worker asking it to look ONLY at the fields we know are None
    execute(db=db_session, columns_to_extract=["scope_content", "admin_bio_history"])

    # The database query must summarily ignore this row in or_(*filters)
    mock_get_engine.return_value.extract.assert_not_called()

    # The document in the database must remain untouched (no execution_log created)
    db_session.expire_all()
    verified_doc = db_session.get(ArchiveDocument, "doc_fantasma")
    assert verified_doc.execution_log is None or "worker_ner_v2" not in verified_doc.execution_log


# ==========================================
# NER EXCLUSIONS — the negative anchoring cycle
# ==========================================


def test_load_entity_blacklist_merges_stopwords_and_exclusions(use_test_db, db_session):
    """Noise and curation decisions share one filter but keep separate origins."""
    db_session.add_all(
        [
            DomainStopwords(word="lixo", word_scope="ENTITY"),
            DomainStopwords(word="generico", word_scope="ALL"),
            DomainStopwords(word="ofício", word_scope="TAG"),  # tag-only: must stay out
            DomainNerExclusion(term="iptu", source="JUDGE"),
        ]
    )
    db_session.commit()

    blacklist = load_entity_blacklist(db_session)

    assert blacklist == {"lixo", "generico", "iptu"}


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_does_not_recreate_an_excluded_entity(mock_get_engine, db_session, generate_archive_doc):
    """THE NEGATIVE CYCLE, end to end.

    The judge decided the term is a TAG, so the exclusion is in the catalog. On the
    next run the engine still returns the same entity (a real spaCy would), and the
    worker must drop it: no entity row, no link, but the document is stamped DONE so
    the queue advances instead of retrying forever.
    """
    mock_get_engine.return_value.extract.return_value = [
        [
            ArchiveEntityDTO(name="IPTU", entity_type="ORG"),
            ArchiveEntityDTO(name="Curitiba", entity_type="LOC"),
        ]
    ]

    doc = generate_archive_doc(
        description_id="doc_excluded",
        original_title="Guia do IPTU",
        scope_content="O IPTU de Curitiba foi reajustado.",
    )
    db_session.add(doc)
    db_session.commit()

    # The curation already settled the clash: "iptu" belongs to the subject axis.
    EntityRepository(db_session).add_ner_exclusions(["iptu"], source="JUDGE", reason="assunto, não entidade")
    db_session.commit()

    execute(db=db_session)

    db_session.expire_all()
    stored_names = set(db_session.scalars(select(ArchiveEntity.name)).all())
    assert "iptu" not in stored_names
    assert "curitiba" in stored_names

    links = db_session.scalars(select(ArchiveDocumentEntity)).all()
    assert len(links) == 1

    assert db_session.get(ArchiveDocument, "doc_excluded").execution_log["worker_ner_v2"] == "DONE"


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_blocks_an_excluded_term_merged_into_a_longer_entity(
    mock_get_engine, db_session, generate_archive_doc
):
    """Regression, found with the real spaCy engine.

    The model merges neighbouring tokens, so excluding "iptu" is not enough when the
    filter compares whole names: the engine returns "IPTU do Batel" and the false
    positive survives the exclusion. The block must work on token boundaries.
    """
    mock_get_engine.return_value.extract.return_value = [
        [
            ArchiveEntityDTO(name="IPTU do Batel", entity_type="LOC"),
            ArchiveEntityDTO(name="Iptuana", entity_type="LOC"),
        ]
    ]

    doc = generate_archive_doc(
        description_id="doc_merged",
        original_title="Guia do IPTU",
        scope_content="O IPTU do Batel foi reajustado.",
    )
    db_session.add(doc)
    db_session.commit()

    EntityRepository(db_session).add_ner_exclusions(["iptu"], source="JUDGE")
    db_session.commit()

    execute(db=db_session)

    db_session.expire_all()
    stored_names = set(db_session.scalars(select(ArchiveEntity.name)).all())
    assert "iptu do batel" not in stored_names
    # Token boundaries hold: a different word containing the letters is untouched.
    assert "iptuana" in stored_names


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_recreates_the_entity_after_the_exclusion_is_removed(
    mock_get_engine, db_session, generate_archive_doc
):
    """The exclusion is reversible: withdrawing it re-opens the extraction.

    This is what makes the mechanism a curation decision instead of a one-way door.
    """
    mock_get_engine.return_value.extract.return_value = [[ArchiveEntityDTO(name="IPTU", entity_type="ORG")]]

    doc = generate_archive_doc(
        description_id="doc_reopened",
        original_title="Guia do IPTU",
        scope_content="O IPTU de Curitiba foi reajustado.",
    )
    db_session.add(doc)
    db_session.commit()

    repo = EntityRepository(db_session)
    repo.add_ner_exclusions(["iptu"], source="JUDGE")
    db_session.commit()
    repo.remove_ner_exclusions(["iptu"])
    db_session.commit()

    execute(db=db_session)

    db_session.expire_all()
    assert set(db_session.scalars(select(ArchiveEntity.name)).all()) == {"iptu"}


def test_excluded_entity_never_comes_back_through_a_synonym_rule(use_test_db, db_session):
    """The exclusion also closes the positive door: the EntityRuler must not receive
    a pattern for a vetoed spelling, otherwise spaCy would re-create it with ``ent_id_``."""
    from scrinalia.domains.archive.models import DomainSynonyms

    entity = ArchiveEntity(name="Iptu", entity_type="ORG")
    db_session.add(entity)
    db_session.commit()

    db_session.add(DomainSynonyms(synonym_name="iptu", category="ORG", canonical_entity_id=entity.entity_id))
    db_session.commit()

    repo = EntityRepository(db_session)
    assert len(repo.get_ner_synonyms_rules()) == 1

    repo.add_ner_exclusions(["iptu"], source="HUMAN")
    db_session.commit()

    assert repo.get_ner_synonyms_rules() == []


def test_purging_tag_stopwords_spares_the_winning_tag(use_test_db, db_session):
    """Regression guard for the collateral damage of storing exclusions as stopwords.

    ``TagRepository.get_stopwords`` used to read every scope, so an ENTITY-scoped ban
    on "iptu" made the subject-axis purge delete the tag the curator had just kept.
    """
    from scrinalia.domains.archive.repository.tag_repo import TagRepository
    from scrinalia.domains.archive.services.tag_service import TagService

    tag = ArchiveTag(name="iptu")
    db_session.add(tag)
    db_session.commit()

    entity = ArchiveEntity(name="IPTU", entity_type="ORG")
    db_session.add(entity)
    db_session.commit()

    EntityRepository(db_session).resolve_cross_domain_conflict(
        winner="TAG", tag_id=tag.tag_id, entity_id=entity.entity_id, source="JUDGE"
    )
    db_session.commit()

    tag_repo = TagRepository(db_session)
    service = TagService(tag_repo, DocumentRepository(db_session))
    deleted = service.purge_stopwords()

    assert deleted == 0
    assert db_session.get(ArchiveTag, tag.tag_id) is not None


def test_entity_scoped_stopword_is_still_honoured_by_the_purge_of_tags(use_test_db, db_session):
    """The scope filter must not break the legitimate TAG/ALL behaviour."""
    from scrinalia.domains.archive.repository.tag_repo import TagRepository

    db_session.add_all([ArchiveTag(name="lixo"), DomainStopwords(word="lixo", word_scope="ALL")])
    db_session.commit()

    assert TagRepository(db_session).get_stopwords() == {"lixo"}


BLOCK = "Acervo de 35.327 fotografias que retratam a cidade de Curitiba no âmbito do Planejamento"


@patch("scrinalia.domains.archive.workers.worker_ner.get_engine")
def test_worker_ner_extracts_from_the_text_without_the_approved_excerpt(
    mock_get_engine,
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """Fase 3.5-B: the boilerplate the archivist discarded stops feeding the extractor."""
    from scrinalia.domains.archive.repository.text_quality_repo import TextQualityRepository
    from scrinalia.domains.archive.schemas.text_quality_schema import TemplateCreateCommand

    generate_archive_doc(description_id="doc_cut", original_title="Rua Izaac", scope_content=BLOCK)
    TextQualityRepository(db_session).create_template(TemplateCreateCommand(text=BLOCK))

    mock_get_engine.return_value.extract.return_value = [[]]
    execute(db=db_session, columns_to_extract=["original_title", "scope_content"])

    assert mock_get_engine.return_value.extract.call_args.args[0] == ["Rua Izaac"]
