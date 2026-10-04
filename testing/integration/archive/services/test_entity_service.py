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


# ==========================================
# MERGE CHAINS (the same defects the tag path had)
# ==========================================


def _merge(repo: EntityRepository, canonical_id: int, ids_to_merge: list[int]) -> None:
    from memoria_curitibana.domains.archive.schemas import MergeEntityCommand
    from memoria_curitibana.domains.archive.services.entity_service import EntityService

    EntityService(repo).merge(MergeEntityCommand(canonical_id=canonical_id, ids_to_merge=ids_to_merge))


def test_chained_entity_merge_keeps_the_mapping_of_the_surviving_canonical(use_test_db, db_session):
    """
    ``a -> b`` then ``b -> c`` must not forget that ``a`` was absorbed.

    ``domain_synonyms.canonical_entity_id`` is ``ON DELETE CASCADE``, so deleting ``b`` used to
    take the synonym of the first merge with it and the extraction recreated the term. Same
    defect and same fix as the tag path.
    """
    from memoria_curitibana.domains.archive.models import DomainSynonyms

    repo = EntityRepository(db_session)
    first = ArchiveEntity(name="prefeiruta", entity_type="ORG")
    second = ArchiveEntity(name="prefeitura", entity_type="ORG")
    third = ArchiveEntity(name="prefeitura de curitiba", entity_type="ORG")
    db_session.add_all([first, second, third])
    db_session.commit()

    _merge(repo, second.entity_id, [first.entity_id])
    db_session.commit()
    _merge(repo, third.entity_id, [second.entity_id])
    db_session.commit()

    mapping = dict(
        db_session.execute(
            select(DomainSynonyms.synonym_name, DomainSynonyms.canonical_entity_id).where(
                DomainSynonyms.category == "ORG"
            )
        ).all()
    )
    assert mapping == {
        "prefeiruta": third.entity_id,
        "prefeitura": third.entity_id,
    }


def test_no_entity_synonym_points_to_a_deleted_entity_after_a_merge_chain(use_test_db, db_session):
    """The cascade must never leave an entity synonym whose canonical is gone."""

    repo = EntityRepository(db_session)
    first = ArchiveEntity(name="ippuc", entity_type="ORG")
    second = ArchiveEntity(name="ippuc.", entity_type="ORG")
    third = ArchiveEntity(name="instituto ippuc", entity_type="ORG")
    db_session.add_all([first, second, third])
    db_session.commit()

    _merge(repo, second.entity_id, [first.entity_id])
    db_session.commit()
    _merge(repo, third.entity_id, [second.entity_id])
    db_session.commit()

    dangling = db_session.execute(
        text(
            """
            SELECT count(*) FROM domain_synonyms ds
            WHERE ds.category IN ('ORG', 'PER', 'LOC')
              AND NOT EXISTS (SELECT 1 FROM archive_entities e WHERE e.entity_id = ds.canonical_entity_id)
            """
        )
    ).scalar_one()

    assert dangling == 0


def test_create_synonyms_repoints_an_existing_entity_mapping(use_test_db, db_session):
    """Re-pointing an entity spelling must move it, not be silently ignored."""
    from memoria_curitibana.domains.archive.schemas import SynonymCommand

    repo = EntityRepository(db_session)
    first = ArchiveEntity(name="ippuc", entity_type="ORG")
    second = ArchiveEntity(name="instituto ippuc", entity_type="ORG")
    db_session.add_all([first, second])
    db_session.commit()

    repo.create_synonyms(
        [
            SynonymCommand(
                synonym_name="ippuc antigo",
                category="ORG",
                canonical_tag_id=None,
                canonical_entity_id=first.entity_id,
            )
        ]
    )
    repo.create_synonyms(
        [
            SynonymCommand(
                synonym_name="ippuc antigo",
                category="ORG",
                canonical_tag_id=None,
                canonical_entity_id=second.entity_id,
            )
        ]
    )
    db_session.flush()

    rules = {rule["pattern"]: rule["id"] for rule in repo.get_ner_synonyms_rules()}
    assert rules["ippuc antigo"] == "instituto ippuc"
