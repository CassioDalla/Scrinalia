from sqlalchemy import select, text

from scrinalia.domains.archive.domain.entity_merge import KIND_MERGE, KIND_RENAME
from scrinalia.domains.archive.models import ArchiveEntity, ArchiveEntityMergeLog, ArchiveTag
from scrinalia.domains.archive.repository import EntityRepository

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
    from scrinalia.domains.archive.models import ArchiveDocumentEntity, ArchiveDocumentTag, ArchiveEntity

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
    from scrinalia.domains.archive.schemas import MergeEntityCommand
    from scrinalia.domains.archive.services.entity_service import EntityService

    EntityService(repo).merge(MergeEntityCommand(canonical_id=canonical_id, ids_to_merge=ids_to_merge))


def test_chained_entity_merge_keeps_the_mapping_of_the_surviving_canonical(use_test_db, db_session):
    """
    ``a -> b`` then ``b -> c`` must not forget that ``a`` was absorbed.

    ``domain_synonyms.canonical_entity_id`` is ``ON DELETE CASCADE``, so deleting ``b`` used to
    take the synonym of the first merge with it and the extraction recreated the term. Same
    defect and same fix as the tag path.
    """
    from scrinalia.domains.archive.models import DomainSynonyms

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
    from scrinalia.domains.archive.schemas import SynonymCommand

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


def test_merge_absorbs_a_cluster_whose_absorbed_names_normalize_to_one_key(use_test_db, db_session):
    """
    The cluster the issue reproduced: ``A. B. Detter`` absorbs ``A. B. Deter`` and ``a. b. deter``.

    ``EntityService.merge`` builds the spellings as a plain list, and two names that differ only in
    case normalize to the same ``(synonym_name, category)``; the single multi-row upsert then made
    PostgreSQL answer ``CardinalityViolation`` and the request failed with a 500, absorbing nothing.
    The write collapses the commands now, so the merge succeeds and the spelling survives exactly
    once.

    The unique index the same change adds to ``archive_entities`` is what makes such a pair
    impossible in a reconciled collection, so the test drops it for its own transaction (the fixture
    rolls the drop back) and puts the two rows back the way the pre-migration collection carries
    them — the exact state the archivist hit.
    """
    from scrinalia.domains.archive.models import DomainSynonyms
    from scrinalia.domains.archive.schemas import MergeEntityCommand
    from scrinalia.domains.archive.services.entity_service import EntityService

    db_session.execute(text("DROP INDEX IF EXISTS uix_archive_entities_name_normalized"))

    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="A. B. Detter", entity_type="PER")
    title_twin = ArchiveEntity(name="A. B. Deter", entity_type="PER")
    lower_twin = ArchiveEntity(name="a. b. deter", entity_type="PER")
    db_session.add_all([canonical, title_twin, lower_twin])
    db_session.commit()

    response = EntityService(repo).merge(
        MergeEntityCommand(
            canonical_id=canonical.entity_id,
            ids_to_merge=[title_twin.entity_id, lower_twin.entity_id],
        )
    )
    db_session.commit()

    assert response.entities_deleted == 2
    mapping = dict(
        db_session.execute(
            select(DomainSynonyms.synonym_name, DomainSynonyms.canonical_entity_id).where(
                DomainSynonyms.category == "PER"
            )
        ).all()
    )
    assert mapping == {"a. b. deter": canonical.entity_id}
    assert db_session.get(ArchiveEntity, title_twin.entity_id) is None
    assert db_session.get(ArchiveEntity, lower_twin.entity_id) is None


# ==========================================
# MERGE PREVIEW AND THE LEDGER (issue #34)
# ==========================================


def test_the_entity_preview_and_the_merge_produce_the_same_numbers(use_test_db, db_session, generate_archive_doc):
    """
    The dry run cannot lie: preview and apply read one planner, so the counts are one measurement.

    This is the tag-merge rule applied to the entity axis, and it is the whole reason the preview is
    a route over ``plan_entity_merge`` instead of a second computation of the impact.
    """
    from scrinalia.domains.archive.models import ArchiveDocumentEntity
    from scrinalia.domains.archive.schemas import MergeEntityCommand, MergeEntityPreviewCommand
    from scrinalia.domains.archive.services.entity_service import EntityService

    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="prefeitura", entity_type="ORG")
    first = ArchiveEntity(name="prefeitura de curitiba", entity_type="ORG")
    second = ArchiveEntity(name="pmc antiga", entity_type="ORG")
    db_session.add_all([canonical, first, second])
    db_session.flush()

    shared = generate_archive_doc(original_title="As duas")
    only_second = generate_archive_doc(original_title="Só a segunda")
    db_session.add_all(
        [
            ArchiveDocumentEntity(description_id=shared.description_id, entity_id=first.entity_id),
            ArchiveDocumentEntity(description_id=only_second.description_id, entity_id=first.entity_id),
            ArchiveDocumentEntity(description_id=only_second.description_id, entity_id=second.entity_id),
            ArchiveDocumentEntity(description_id=shared.description_id, entity_id=canonical.entity_id),
        ]
    )
    db_session.flush()

    service = EntityService(repo)
    preview = service.preview_merge(
        MergeEntityPreviewCommand(
            canonical_id=canonical.entity_id,
            ids_to_merge=[first.entity_id, second.entity_id],
            new_name="pmc",
        )
    )
    response = service.merge(
        MergeEntityCommand(
            canonical_id=canonical.entity_id,
            ids_to_merge=[first.entity_id, second.entity_id],
            new_name="pmc",
            changed_by=None,
        )
    )
    db_session.flush()

    assert preview.documents_updated == response.documents_updated == 2
    # The links are the absorbed entities' own (2 + 1); the documents are the union (2), never the sum.
    assert preview.links_rewritten == 3
    assert len(preview.entities_deleted) == response.entities_deleted == 2
    assert preview.renamed_from == "prefeitura"
    assert preview.renamed_to == "pmc"
    # One ledger row per absorbed entity: the handles the screen needs to undo the click.
    assert len(response.merge_ids) == 2


def test_rename_entity_is_one_definition_shared_with_the_merge(use_test_db, db_session):
    """
    The single-entity rename and the merge's optional rename write the same two things.

    The old spelling becomes a synonym so the extractor keeps resolving it; the new spelling is what
    the catalogue shows. One method owns that pair, so the two entry points cannot drift.
    """
    from scrinalia.domains.archive.services.entity_service import EntityService

    repo = EntityRepository(db_session)
    entity = ArchiveEntity(name="prefeitura muinicipal", entity_type="ORG")
    db_session.add(entity)
    db_session.flush()

    renamed, merge_id = EntityService(repo).rename_entity(entity.entity_id, "prefeitura municipal")
    db_session.flush()

    assert renamed.name == "prefeitura municipal"
    assert renamed.entity_type == "ORG"
    assert repo.get_entity_synonym_targets(["prefeitura muinicipal"], "ORG") == {
        "prefeitura muinicipal": entity.entity_id
    }

    # One row, and it is a RENAME: it is what makes the pencil on the screen reversible.
    row = db_session.get(ArchiveEntityMergeLog, merge_id)
    assert row is not None
    assert row.kind == KIND_RENAME
    assert row.canonical_renamed_from == "prefeitura muinicipal"
    assert row.canonical_name == "prefeitura municipal"
    # No absorbed entity, and no links invented that the undo would then remove.
    assert row.absorbed_entity_id is None
    assert row.absorbed_snapshot is None
    assert row.document_ids == []
    assert row.renamed_from_synonym_created is True


def test_undoing_a_rename_puts_the_name_back_and_drops_the_spelling_it_planted(use_test_db, db_session):
    """The undo is the same one the merge uses, because it is the same ledger."""
    from scrinalia.domains.archive.services.entity_service import EntityService

    repo = EntityRepository(db_session)
    entity = ArchiveEntity(name="prefeitura muinicipal", entity_type="ORG")
    db_session.add(entity)
    db_session.flush()

    _, merge_id = EntityService(repo).rename_entity(entity.entity_id, "prefeitura municipal")
    db_session.flush()

    repo.undo_entity_merge(merge_id)
    db_session.flush()

    assert db_session.get(ArchiveEntity, entity.entity_id).name == "prefeitura muinicipal"
    # The spelling the rename planted is gone: leaving it would keep the corrected typo alive as an
    # alias of the entity, which is exactly what the archivist undid.
    assert repo.get_entity_synonym_targets(["prefeitura muinicipal"], "ORG") == {}


def test_a_rename_can_decline_to_anchor_the_old_spelling(use_test_db, db_session):
    """
    Correcting a typo is not the same decision as unifying two spellings, so it is offered.

    ``Prefeitura Muinicipal`` is not a spelling anybody should keep, and anchoring it is what the
    toggle turns off. The ledger row still records the previous name, so the undo is the same.
    """
    from scrinalia.domains.archive.services.entity_service import EntityService

    repo = EntityRepository(db_session)
    entity = ArchiveEntity(name="prefeitura muinicipal", entity_type="ORG")
    db_session.add(entity)
    db_session.flush()

    _, merge_id = EntityService(repo).rename_entity(entity.entity_id, "prefeitura municipal", keep_old_synonym=False)
    db_session.flush()

    assert repo.get_entity_synonym_targets(["prefeitura muinicipal"], "ORG") == {}
    row = db_session.get(ArchiveEntityMergeLog, merge_id)
    assert row is not None
    assert row.renamed_from_synonym_created is False

    repo.undo_entity_merge(merge_id)
    db_session.flush()
    assert db_session.get(ArchiveEntity, entity.entity_id).name == "prefeitura muinicipal"


def test_renaming_onto_a_spelling_that_exists_names_the_twin(use_test_db, db_session):
    """
    The collision is a 409 that names the twin, not a structural conflict.

    ``uix_archive_entities_name_normalized`` would raise an ``IntegrityError`` and the archivist would
    read "Conflito estrutural no banco de dados" — which names neither the twin nor the fact that the
    twin is the merge case. The refusal carries both, as data, so the screen can say it.
    """
    import pytest

    from scrinalia.domains.archive.exceptions import DuplicateEntityNameError
    from scrinalia.domains.archive.services.entity_service import EntityService

    repo = EntityRepository(db_session)
    first = ArchiveEntity(name="smu", entity_type="ORG")
    second = ArchiveEntity(name="Secretaria Municipal do Urbanismo", entity_type="ORG")
    db_session.add_all([first, second])
    db_session.flush()

    with pytest.raises(DuplicateEntityNameError) as refusal:
        EntityService(repo).rename_entity(second.entity_id, "SMU")

    assert refusal.value.conflicting_entity_id == first.entity_id
    assert refusal.value.conflicting_name == "smu"
    assert refusal.value.details == {
        "entity": {"entity_id": second.entity_id, "name": "SMU"},
        "conflicting_entity": {"entity_id": first.entity_id, "name": "smu"},
    }
    # Refused before the write: the entity keeps the name it had and no ledger row was left behind.
    assert db_session.get(ArchiveEntity, second.entity_id).name == "Secretaria Municipal do Urbanismo"


def test_a_merge_with_a_rename_leaves_one_row_per_absorbed_entity_and_no_rename_row(use_test_db, db_session):
    """
    The merge's optional rename must not log a second row.

    ``apply_entity_merge`` calls the same ``rename_entity`` the standalone route calls, and its own row
    already carries ``canonical_renamed_from``. A writer inside ``rename_entity`` would put two rows
    under one decision — and undoing the RENAME row alone would then rename the canonical back while
    its absorbed twin stayed deleted.
    """
    from scrinalia.domains.archive.schemas.command_schema import MergeEntityCommand
    from scrinalia.domains.archive.services.entity_service import EntityService

    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="prefeitura de curitiba", entity_type="ORG")
    absorbed = ArchiveEntity(name="pmc", entity_type="ORG")
    db_session.add_all([canonical, absorbed])
    db_session.flush()

    response = EntityService(repo).merge(
        MergeEntityCommand(
            canonical_id=canonical.entity_id,
            ids_to_merge=[absorbed.entity_id],
            new_name="prefeitura municipal de curitiba",
        )
    )
    db_session.flush()

    assert db_session.get(ArchiveEntity, canonical.entity_id).name == "prefeitura municipal de curitiba"
    rows = db_session.scalars(select(ArchiveEntityMergeLog)).all()
    assert [row.kind for row in rows] == [KIND_MERGE]
    assert len(rows) == len(response.merge_ids) == 1
    assert rows[0].canonical_renamed_from == "prefeitura de curitiba"
