from sqlalchemy import select, text

from domains.archive.models import ArchiveDocument, ArchiveEntity, DomainSynonyms
from domains.archive.repository.entity_repo import EntityRepository
from domains.archive.schemas.entity_schema import ArchiveEntityDTO


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
    assert rules[0]["canonical_name"] == "Prefeitura de Curitiba"


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
