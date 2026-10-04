from sqlalchemy import select, text

from memoria_curitibana.domains.archive.models import (
    ArchiveDocument,
    ArchiveEntity,
    ArchiveTag,
    DomainNerExclusion,
    DomainStopwords,
    DomainSynonyms,
)
from memoria_curitibana.domains.archive.repository.entity_repo import EntityRepository
from memoria_curitibana.domains.archive.schemas.entity_schema import ArchiveEntityDTO


def test_get_or_create_entities_new_and_existing(use_test_db, db_session):
    """Guarantees entity creation and idempotency (NER)."""
    repo = EntityRepository(db_session)
    entities_dto = [ArchiveEntityDTO(name="David Carneiro", entity_type="PER")]

    ids_step_1 = repo.get_or_create_entities(entities_dto)
    db_session.commit()

    ids_step_2 = repo.get_or_create_entities(entities_dto)
    db_session.commit()

    assert len(ids_step_1) == 1
    assert ids_step_1[0] == ids_step_2[0]


def test_get_or_create_entities_is_case_insensitive(use_test_db, db_session):
    """Regression: 'Curitiba' and 'curitiba' must resolve to the same canonical entity."""
    repo = EntityRepository(db_session)

    id_upper = repo.get_or_create_entities([ArchiveEntityDTO(name="Curitiba", entity_type="LOC")])
    db_session.commit()

    id_mixed = repo.get_or_create_entities([ArchiveEntityDTO(name="CURITIBA", entity_type="LOC")])
    db_session.commit()

    assert id_upper == id_mixed

    stored = db_session.scalars(select(ArchiveEntity)).all()
    assert len(stored) == 1
    assert stored[0].name == "curitiba"


def test_get_ner_synonyms_rules(use_test_db, db_session):
    """Tests the SQL join that builds the spaCy patterns based on the official Synonyms table."""
    repo = EntityRepository(db_session)

    # 1. Create the Canonical Entity
    canonical_entity = ArchiveEntity(name="Prefeitura de Curitiba", entity_type="ORG")
    db_session.add(canonical_entity)
    db_session.commit()

    # 2. Create the Synonym pointing to the Entity
    synonym = DomainSynonyms(
        synonym_name="prefeitura municipal", category="ORG", canonical_entity_id=canonical_entity.entity_id
    )
    db_session.add(synonym)
    db_session.commit()

    # 3. Run the query
    rules = repo.get_ner_synonyms_rules()

    assert len(rules) == 1
    assert rules[0]["pattern"] == "prefeitura municipal"
    assert rules[0]["label"] == "ORG"
    # spaCy reads the canonical entity from the "id" key (exposed as ent_id_).
    assert rules[0]["id"] == "Prefeitura de Curitiba"


def test_purge_orphan_entities(use_test_db, db_session):
    """Guarantees that only entities without linked documents are deleted."""
    repo = EntityRepository(db_session)

    orphan_entity = ArchiveEntity(name="Fantasma", entity_type="PER")
    used_entity = ArchiveEntity(name="Útil", entity_type="LOC")
    doc = ArchiveDocument(description_id="doc_1", staging_content_hash="hash", original_title="AAA")

    db_session.add_all([orphan_entity, used_entity, doc])
    db_session.commit()

    # Link only the useful entity
    repo.link_entities_to_document("doc_1", [used_entity.entity_id])
    db_session.commit()

    # Clean the orphans
    deleted_count = repo.purge_orphan_entities()
    db_session.commit()

    assert deleted_count == 1

    # Check the database state
    remaining_entities = db_session.scalars(select(ArchiveEntity)).all()
    assert len(remaining_entities) == 1
    assert remaining_entities[0].name == "Útil"


def test_find_similar_trgm(use_test_db, db_session):
    """Tests the integration with the PostgreSQL pg_trgm extension."""

    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    db_session.commit()

    repo = EntityRepository(db_session)

    db_session.add_all(
        [
            ArchiveEntity(name="Winston Churchill", entity_type="PER"),
            ArchiveEntity(name="Winstn Churchil", entity_type="PER"),
            ArchiveEntity(name="Winston Chuechill", entity_type="LOC"),  # Intentional type error
            ArchiveEntity(name="Getúlio Vargas", entity_type="PER"),
        ]
    )
    db_session.commit()

    # Search for something similar (target must be lowercase due to the Service business rule)
    results = repo.find_similar("winston churchill", entity_type=None, threshold=0.5)

    # Must find the two typos, ignoring itself and Getúlio
    assert len(results) == 2
    found_names = [r.name for r in results]
    assert "Winstn Churchil" in found_names
    assert "Winston Chuechill" in found_names


# ==========================================
# NER EXCLUSIONS (the subject axis owns the term)
# ==========================================


def test_add_ner_exclusions_is_idempotent_and_normalized(use_test_db, db_session):
    """The same term cannot be excluded twice, and the stored spelling is lowercase."""
    repo = EntityRepository(db_session)

    inserted_first = repo.add_ner_exclusions(["  IPTU ", "IPTU"], source="JUDGE", tag_id=None)
    db_session.commit()
    inserted_again = repo.add_ner_exclusions(["iptu"])
    db_session.commit()

    assert inserted_first == 1
    assert inserted_again == 0

    stored = db_session.scalars(select(DomainNerExclusion)).all()
    assert len(stored) == 1
    assert stored[0].term == "iptu"
    assert stored[0].source == "JUDGE"


def test_add_ner_exclusions_ignores_blank_terms(use_test_db, db_session):
    """Whitespace-only terms never reach the catalog."""
    repo = EntityRepository(db_session)

    assert repo.add_ner_exclusions(["   ", ""]) == 0
    assert db_session.scalars(select(DomainNerExclusion)).all() == []


def test_get_ner_exclusion_terms_returns_lowercase_set(use_test_db, db_session):
    """The worker consumes this as a plain set for O(1) filtering."""
    repo = EntityRepository(db_session)
    repo.add_ner_exclusions(["IPTU", "Batel"])
    db_session.commit()

    assert repo.get_ner_exclusion_terms() == {"iptu", "batel"}


def test_remove_ner_exclusions_reopens_the_term(use_test_db, db_session):
    """Undoing an exclusion removes exactly that term."""
    repo = EntityRepository(db_session)
    repo.add_ner_exclusions(["iptu", "batel"])
    db_session.commit()

    removed = repo.remove_ner_exclusions(["IPTU"])
    db_session.commit()

    assert removed == 1
    assert repo.get_ner_exclusion_terms() == {"batel"}


def test_remove_ner_exclusions_ignores_unknown_terms(use_test_db, db_session):
    """Removing something that was never excluded is a no-op, not an error."""
    repo = EntityRepository(db_session)

    assert repo.remove_ner_exclusions(["nunca-existiu"]) == 0


def test_list_ner_exclusions_exposes_provenance(use_test_db, db_session):
    """The catalog is readable by the curation API with its justification and origin."""
    repo = EntityRepository(db_session)
    tag = ArchiveTag(name="iptu")
    db_session.add(tag)
    db_session.commit()

    repo.add_ner_exclusions(["iptu"], source="HUMAN", reason="é assunto, não entidade", tag_id=tag.tag_id)
    db_session.commit()

    listed = list(repo.list_ner_exclusions())

    assert len(listed) == 1
    assert listed[0].term == "iptu"
    assert listed[0].source == "HUMAN"
    assert listed[0].reason == "é assunto, não entidade"
    assert listed[0].tag_id == tag.tag_id


def test_excluded_term_is_never_a_ner_synonym_rule(use_test_db, db_session):
    """A vetoed spelling must not re-enter through the positive dictionary either."""
    repo = EntityRepository(db_session)

    entity = ArchiveEntity(name="Iptu", entity_type="ORG")
    db_session.add(entity)
    db_session.commit()

    db_session.add(DomainSynonyms(synonym_name="iptu", category="ORG", canonical_entity_id=entity.entity_id))
    db_session.commit()

    assert len(repo.get_ner_synonyms_rules()) == 1

    repo.add_ner_exclusions(["iptu"], source="JUDGE")
    db_session.commit()

    assert repo.get_ner_synonyms_rules() == []


def test_exclusion_survives_the_deletion_of_its_tag(use_test_db, db_session):
    """Regression guard: the FK is SET NULL, not CASCADE — deleting a tag must not
    silently re-open the NER false positive the exclusion exists to prevent."""
    repo = EntityRepository(db_session)
    tag = ArchiveTag(name="iptu")
    db_session.add(tag)
    db_session.commit()

    repo.add_ner_exclusions(["iptu"], source="HUMAN", tag_id=tag.tag_id)
    db_session.commit()

    db_session.delete(tag)
    db_session.commit()

    remaining = db_session.scalars(select(DomainNerExclusion)).all()
    assert len(remaining) == 1
    assert remaining[0].term == "iptu"
    assert remaining[0].tag_id is None


def test_exclusion_replaces_the_entity_stopword(use_test_db, db_session, generate_archive_doc):
    """When the TAG wins, the decision lands in the exclusion catalog, not in the
    generic stopword blacklist: a subject term is a decision, not noise."""
    repo = EntityRepository(db_session)

    tag = ArchiveTag(name="iptu")
    entity = ArchiveEntity(name="IPTU", entity_type="ORG")
    doc = generate_archive_doc(description_id="doc_iptu", original_title="Guia do IPTU")
    db_session.add_all([tag, entity, doc])
    db_session.commit()

    repo.link_entities_to_document("doc_iptu", [entity.entity_id])
    db_session.commit()

    repo.resolve_cross_domain_conflict(winner="TAG", tag_id=tag.tag_id, entity_id=entity.entity_id, source="JUDGE")
    db_session.commit()

    exclusions = db_session.scalars(select(DomainNerExclusion)).all()
    assert len(exclusions) == 1
    assert exclusions[0].term == "iptu"
    assert exclusions[0].source == "JUDGE"
    assert exclusions[0].tag_id == tag.tag_id

    entity_stopwords = db_session.scalars(select(DomainStopwords).where(DomainStopwords.word_scope == "ENTITY")).all()
    assert entity_stopwords == []


def test_resolve_cross_domain_conflict_entity_wins_keeps_tag_stopword(use_test_db, db_session):
    """The other direction is untouched: when the ENTITY wins, the tag name joins the
    tag-scoped stopwords so the subject axis stops recreating it."""
    repo = EntityRepository(db_session)

    tag = ArchiveTag(name="batel")
    entity = ArchiveEntity(name="Batel", entity_type="LOC")
    db_session.add_all([tag, entity])
    db_session.commit()

    repo.resolve_cross_domain_conflict(winner="ENTITY", tag_id=tag.tag_id, entity_id=entity.entity_id)
    db_session.commit()

    stopwords = db_session.scalars(select(DomainStopwords)).all()
    assert len(stopwords) == 1
    assert stopwords[0].word == "batel"
    assert stopwords[0].word_scope == "TAG"
    assert db_session.scalars(select(DomainNerExclusion)).all() == []
