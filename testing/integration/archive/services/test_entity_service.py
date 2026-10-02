from sqlalchemy import select, text

from memoria_curitibana.domains.archive.models import ArchiveEntity, ArchiveTag
from memoria_curitibana.domains.archive.repository import EntityRepository

# ==========================================
# CROSS-DOMAIN CLASH TESTS
# ==========================================


def test_get_cross_domain_conflicts(use_test_db, db_session):
    """Tests whether pg_trgm finds real conflicts between the independent tables."""

    db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    db_session.commit()

    repo = EntityRepository(db_session)

    # We create a conflict scenario: "Batel" exists as a Tag and as an Entity (LOC)
    db_session.add_all(
        [
            ArchiveTag(name="batel"),
            ArchiveEntity(name="Batel", entity_type="LOC"),
            ArchiveTag(name="ofício"),  # No conflict
            ArchiveEntity(name="David Carneiro", entity_type="PER"),  # No conflict
        ]
    )
    db_session.commit()

    conflicts = repo.get_cross_domain_conflicts(threshold=0.85)

    assert len(conflicts) == 1
    assert conflicts[0].tag_name == "batel"
    assert conflicts[0].entity_name == "Batel"
    assert conflicts[0].similarity >= 0.99  # They are the same word


def test_resolve_cross_domain_conflict_tag_wins(use_test_db, db_session, generate_archive_doc):
    """Guarantees that the Tag absorbs the Entity's documents and the Entity is destroyed."""
    from memoria_curitibana.domains.archive.models import ArchiveDocumentEntity, ArchiveDocumentTag, ArchiveEntity

    repo = EntityRepository(db_session)

    tag = ArchiveTag(name="urbanismo")
    ent = ArchiveEntity(name="Urbanismo", entity_type="ORG")
    entity_doc = generate_archive_doc(description_id="doc_1", original_title="Teste")

    db_session.add_all([tag, ent, entity_doc])
    db_session.commit()

    # Link the document ONLY to the Entity
    db_session.add(ArchiveDocumentEntity(description_id="doc_1", entity_id=ent.entity_id))
    db_session.commit()

    # THE MAGIC: The Tag wins the conflict
    moved_docs = repo.resolve_cross_domain_conflict(winner="TAG", tag_id=tag.tag_id, entity_id=ent.entity_id)
    db_session.commit()

    assert moved_docs == 1

    # The entity must have ceased to exist
    db_entity = db_session.get(ArchiveEntity, ent.entity_id)
    assert db_entity is None

    # The document must now be in the ArchiveDocumentTag table!
    new_link = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert len(new_link) == 1
    assert new_link[0].tag_id == tag.tag_id
