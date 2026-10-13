"""
Integration tests of the entity-merge ledger: the undo has to be exact, not approximate.

The promise of the curation flow is that a merge a human approved can be reverted by a human.
These tests pin the two halves of that promise for the entity axis: the ledger records enough
(the row, the per-entity links, the spelling state and the name the canonical lost) and the undo
restores exactly that state — including the links the merge created, which must disappear, and the
ones that already existed, which must not.
"""

import pytest
from sqlalchemy import delete, select

from scrinalia.core.author import Author
from scrinalia.domains.archive.exceptions import (
    MergeAlreadyUndoneError,
    MergeLogNotFoundError,
)
from scrinalia.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentEntity,
    ArchiveEntity,
)
from scrinalia.domains.archive.repository.entity_repo import EntityRepository
from scrinalia.domains.archive.schemas import ArchiveEntityDTO, SynonymCommand


def _link(db_session, entity: ArchiveEntity, document_id: str) -> None:
    db_session.add(ArchiveDocumentEntity(description_id=document_id, entity_id=entity.entity_id))


def _merge(repo: EntityRepository, canonical_id: int, ids_to_merge: list[int], new_name: str | None = None):
    plan = repo.plan_entity_merge(canonical_id, ids_to_merge, new_name)
    return repo.apply_entity_merge(plan)


def test_apply_entity_merge_writes_one_ledger_row_per_absorbed_entity(use_test_db, db_session, generate_archive_doc):
    """The ledger keeps the snapshot, the exact links and who did it."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="rua", entity_type="LOC")
    variant = ArchiveEntity(name="ruas", entity_type="LOC")
    db_session.add_all([canonical, variant])
    db_session.flush()

    docs = [generate_archive_doc(original_title=f"Doc {index}") for index in range(2)]
    for doc in docs:
        _link(db_session, variant, doc.description_id)
    db_session.flush()

    plan = repo.plan_entity_merge(canonical.entity_id, [variant.entity_id])
    response = repo.apply_entity_merge(plan, changed_by=Author(name="arquivista"), note="mesmo lugar")
    db_session.flush()

    assert response.merge_ids == [entry.merge_id for entry in repo.list_entity_merge_log()]

    log = repo.list_entity_merge_log()
    assert repo.count_entity_merge_log() == 1
    entry = log[0]
    assert entry.absorbed_name == "ruas"
    assert entry.absorbed_entity_type == "LOC"
    assert entry.canonical_name == "rua"
    assert entry.changed_by == "arquivista"
    assert entry.note == "mesmo lugar"
    assert entry.document_count == 2
    assert entry.undone_at is None
    assert entry.synonym_created is True
    assert entry.is_undone is False


def test_undo_entity_merge_restores_the_entity_the_links_and_the_type(use_test_db, db_session, generate_archive_doc):
    """Undo is lossless: id, name, type and links all come back."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="prefeitura", entity_type="ORG")
    variant = ArchiveEntity(name="prefeitura antiga", entity_type="ORG")
    db_session.add_all([canonical, variant])
    db_session.flush()
    restored_id = variant.entity_id
    created_at = variant.created_at

    doc = generate_archive_doc(original_title="Doc")
    _link(db_session, variant, doc.description_id)
    db_session.flush()

    merge_id = _merge(repo, canonical.entity_id, [variant.entity_id]).merge_ids[0]
    db_session.flush()
    assert db_session.get(ArchiveEntity, restored_id) is None  # the entity is really gone

    entry = repo.undo_entity_merge(merge_id, undone_by=Author(name="arquivista"))
    db_session.flush()

    restored = db_session.get(ArchiveEntity, restored_id)
    assert restored is not None
    assert restored.name == "prefeitura antiga"
    assert restored.entity_type == "ORG"
    assert restored.created_at == created_at

    links = db_session.scalars(select(ArchiveDocumentEntity)).all()
    assert [(link.description_id, link.entity_id) for link in links] == [(doc.description_id, restored_id)]
    assert entry.undone_by == "arquivista"
    assert entry.is_undone is True


def test_undo_entity_merge_removes_only_the_links_the_merge_created(use_test_db, db_session, generate_archive_doc):
    """
    A document that already carried the canonical keeps it; the new links disappear.

    Restoring the entity without removing the links the merge created would leave the document
    with both spellings — not the state the archivist had before approving.
    """
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="rua", entity_type="LOC")
    variant = ArchiveEntity(name="ruas", entity_type="LOC")
    db_session.add_all([canonical, variant])
    db_session.flush()

    only_variant = generate_archive_doc(original_title="Só a variante")
    both = generate_archive_doc(original_title="As duas")
    _link(db_session, variant, only_variant.description_id)
    _link(db_session, variant, both.description_id)
    _link(db_session, canonical, both.description_id)
    db_session.flush()

    merge_id = _merge(repo, canonical.entity_id, [variant.entity_id]).merge_ids[0]
    db_session.flush()

    repo.undo_entity_merge(merge_id)
    db_session.flush()

    links = db_session.scalars(select(ArchiveDocumentEntity).order_by(ArchiveDocumentEntity.description_id)).all()
    state = {(link.description_id, link.entity_id) for link in links}
    assert state == {
        (only_variant.description_id, variant.entity_id),
        (both.description_id, variant.entity_id),
        (both.description_id, canonical.entity_id),
    }


def test_undo_entity_merge_moves_back_the_spellings_that_pointed_at_the_absorbed_entity(use_test_db, db_session):
    """A spelling absorbed by an earlier merge follows the entity when it is restored."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="prefeitura", entity_type="ORG")
    variant = ArchiveEntity(name="prefeitura de curitiba", entity_type="ORG")
    db_session.add_all([canonical, variant])
    db_session.flush()
    restored_id = variant.entity_id

    repo.create_synonyms(
        [
            SynonymCommand(
                synonym_name="pmc", category="ORG", canonical_tag_id=None, canonical_entity_id=variant.entity_id
            )
        ]
    )
    db_session.flush()

    merge_id = _merge(repo, canonical.entity_id, [variant.entity_id]).merge_ids[0]
    db_session.flush()
    assert repo.get_entity_synonym_targets(["pmc"], "ORG") == {"pmc": canonical.entity_id}

    repo.undo_entity_merge(merge_id)
    db_session.flush()

    assert repo.get_entity_synonym_targets(["pmc"], "ORG") == {"pmc": restored_id}
    # The spelling created for the absorbed name is gone, exactly as before the merge.
    assert repo.get_entity_synonym_targets(["prefeitura de curitiba"], "ORG") == {}


def test_undo_entity_merge_restores_a_spelling_that_already_pointed_somewhere_else(use_test_db, db_session):
    """When the spelling already existed, undo puts it back where it was instead of deleting it."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="rua", entity_type="LOC")
    variant = ArchiveEntity(name="ruas", entity_type="LOC")
    other = ArchiveEntity(name="logradouro", entity_type="LOC")
    db_session.add_all([canonical, variant, other])
    db_session.flush()

    repo.create_synonyms(
        [
            SynonymCommand(
                synonym_name="ruas", category="LOC", canonical_tag_id=None, canonical_entity_id=other.entity_id
            )
        ]
    )
    db_session.flush()

    merge_id = _merge(repo, canonical.entity_id, [variant.entity_id]).merge_ids[0]
    db_session.flush()
    assert repo.get_entity_synonym_targets(["ruas"], "LOC") == {"ruas": canonical.entity_id}

    repo.undo_entity_merge(merge_id)
    db_session.flush()

    assert repo.get_entity_synonym_targets(["ruas"], "LOC") == {"ruas": other.entity_id}


def test_undo_entity_merge_restores_the_canonical_name_the_merge_renamed(use_test_db, db_session):
    """The optional rename is part of the same write, so the undo puts the old name back."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="prefeitura", entity_type="ORG")
    variant = ArchiveEntity(name="prefeitura de curitiba", entity_type="ORG")
    db_session.add_all([canonical, variant])
    db_session.flush()
    canonical_id = canonical.entity_id

    merge_id = _merge(repo, canonical_id, [variant.entity_id], new_name="pmc").merge_ids[0]
    db_session.flush()

    renamed = db_session.get(ArchiveEntity, canonical_id)
    assert renamed is not None and renamed.name == "pmc"
    assert repo.get_entity_synonym_targets(["prefeitura"], "ORG") == {"prefeitura": canonical_id}

    entry = repo.undo_entity_merge(merge_id)
    db_session.flush()

    restored = db_session.get(ArchiveEntity, canonical_id)
    assert restored is not None and restored.name == "prefeitura"
    assert entry.canonical_renamed_from == "prefeitura"
    # Both spellings the merge planted are gone: the old canonical name and the absorbed one.
    assert repo.get_entity_synonym_targets(["prefeitura"], "ORG") == {}
    assert repo.get_entity_synonym_targets(["prefeitura de curitiba"], "ORG") == {}


def test_undo_entity_merge_is_single_shot(use_test_db, db_session):
    """The ledger keeps one reversal per merge; a second one is a conflict, not a silent no-op."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="casa", entity_type="LOC")
    variant = ArchiveEntity(name="casas", entity_type="LOC")
    db_session.add_all([canonical, variant])
    db_session.flush()

    merge_id = _merge(repo, canonical.entity_id, [variant.entity_id]).merge_ids[0]
    db_session.flush()
    repo.undo_entity_merge(merge_id)

    with pytest.raises(MergeAlreadyUndoneError):
        repo.undo_entity_merge(merge_id)


def test_undo_unknown_entity_merge_raises_not_found(use_test_db, db_session):
    """An unknown ledger id is a 404, never an empty success."""
    with pytest.raises(MergeLogNotFoundError):
        EntityRepository(db_session).undo_entity_merge(999_999)


def test_undo_entity_merge_tolerates_a_document_deleted_after_the_merge(use_test_db, db_session, generate_archive_doc):
    """A document that no longer exists must not make the undo impossible."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="lote", entity_type="LOC")
    variant = ArchiveEntity(name="lotes", entity_type="LOC")
    db_session.add_all([canonical, variant])
    db_session.flush()

    doc = generate_archive_doc(original_title="Doc")
    _link(db_session, variant, doc.description_id)
    db_session.flush()

    merge_id = _merge(repo, canonical.entity_id, [variant.entity_id]).merge_ids[0]
    db_session.flush()

    db_session.execute(delete(ArchiveDocument).where(ArchiveDocument.description_id == doc.description_id))
    db_session.flush()

    entry = repo.undo_entity_merge(merge_id)
    db_session.flush()

    assert entry.document_count == 1  # what the ledger recorded
    assert db_session.get(ArchiveEntity, variant.entity_id) is not None
    assert (
        db_session.scalars(
            select(ArchiveDocumentEntity).where(ArchiveDocumentEntity.entity_id == variant.entity_id)
        ).all()
        == []
    )


def test_the_sequence_survives_an_entity_undo(use_test_db, db_session):
    """Restoring an old id must not collide with the next entity the ingestion creates."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="igreja", entity_type="LOC")
    variant = ArchiveEntity(name="igrejas", entity_type="LOC")
    db_session.add_all([canonical, variant])
    db_session.flush()

    merge_id = _merge(repo, canonical.entity_id, [variant.entity_id]).merge_ids[0]
    db_session.flush()
    repo.undo_entity_merge(merge_id)
    db_session.flush()

    new_ids = repo.get_or_create_entities(
        [
            ArchiveEntityDTO(name="nova entidade", entity_type="ORG"),
            ArchiveEntityDTO(name="outra entidade", entity_type="ORG"),
        ]
    )
    db_session.flush()

    assert len(set(new_ids)) == 2
    assert db_session.get(ArchiveEntity, variant.entity_id) is not None


def test_entity_merge_log_is_paginated_and_filtered(use_test_db, db_session):
    """The audit trail reports the total and filters by canonical, author and undone state."""
    repo = EntityRepository(db_session)
    pairs = [("casa", "casas"), ("obra", "obras"), ("lote", "lotes")]
    merge_ids = []
    for index, (canonical_name, variant_name) in enumerate(pairs):
        canonical = ArchiveEntity(name=canonical_name, entity_type="LOC")
        variant = ArchiveEntity(name=variant_name, entity_type="LOC")
        db_session.add_all([canonical, variant])
        db_session.flush()
        author = "arquivista" if index < 2 else "outro"
        response = repo.apply_entity_merge(
            repo.plan_entity_merge(canonical.entity_id, [variant.entity_id]), changed_by=Author(name=author)
        )
        merge_ids.append(response.merge_ids[0])
    db_session.flush()

    assert repo.count_entity_merge_log() == 3
    assert repo.count_entity_merge_log(changed_by_name="arquivista") == 2
    assert repo.count_entity_merge_log(canonical_id=999_999) == 0

    first_canonical = db_session.scalar(select(ArchiveEntity).where(ArchiveEntity.name == "casa"))
    assert repo.count_entity_merge_log(canonical_id=first_canonical.entity_id) == 1

    assert len(repo.list_entity_merge_log(limit=2)) == 2
    assert len(repo.list_entity_merge_log(limit=2, offset=2)) == 1

    repo.undo_entity_merge(merge_ids[0])
    db_session.flush()
    assert repo.count_entity_merge_log(include_undone=False) == 2
    assert repo.count_entity_merge_log(include_undone=True) == 3


def test_the_entity_ledger_searches_both_sides_of_the_entry(db_session) -> None:
    """The archivist asking "where did this spelling go?" does not know which side it was on."""
    repo = EntityRepository(db_session)
    for canonical_name, variant_name in (("avenida paulista", "av. paulista"), ("casa", "casas")):
        canonical = ArchiveEntity(name=canonical_name, entity_type="LOC")
        variant = ArchiveEntity(name=variant_name, entity_type="LOC")
        db_session.add_all([canonical, variant])
        db_session.flush()
        _merge(repo, canonical.entity_id, [variant.entity_id])
    db_session.flush()

    assert repo.count_entity_merge_log(term="avenida") == 1
    assert repo.count_entity_merge_log(term="av.") == 1
    assert repo.count_entity_merge_log(term="paulista") == 1
    assert repo.count_entity_merge_log(term="casas") == 1
    assert repo.count_entity_merge_log(term="nada disso") == 0

    assert len(repo.list_entity_merge_log(term="paulista")) == repo.count_entity_merge_log(term="paulista")


def test_a_wildcard_in_the_entity_ledger_search_is_a_character(db_session) -> None:
    """``%`` must not mean "everything": the ledger would answer the whole trail to a typo."""
    repo = EntityRepository(db_session)
    for canonical_name, variant_name in (("casa", "casas"), ("cem por cento", "100%")):
        canonical = ArchiveEntity(name=canonical_name, entity_type="LOC")
        variant = ArchiveEntity(name=variant_name, entity_type="LOC")
        db_session.add_all([canonical, variant])
        db_session.flush()
        _merge(repo, canonical.entity_id, [variant.entity_id])
    db_session.flush()

    assert repo.count_entity_merge_log(term="%") == 1
    assert repo.count_entity_merge_log(term="_") == 0


def test_the_ledger_exposes_the_synonym_mapping_it_restores(db_session) -> None:
    """The row carries the spelling state the undo needs, not a count of it."""
    repo = EntityRepository(db_session)
    canonical = ArchiveEntity(name="instituto", entity_type="ORG")
    variant = ArchiveEntity(name="instituto antigo", entity_type="ORG")
    db_session.add_all([canonical, variant])
    db_session.flush()

    repo.create_synonyms(
        [
            SynonymCommand(
                synonym_name="ippuc",
                category="ORG",
                canonical_tag_id=None,
                canonical_entity_id=variant.entity_id,
            )
        ]
    )
    db_session.flush()

    entry_id = _merge(repo, canonical.entity_id, [variant.entity_id]).merge_ids[0]
    db_session.flush()

    entry = repo.get_entity_merge_log_entry(entry_id)
    assert entry is not None
    assert entry.repointed_synonym_names == ["ippuc"]
    assert repo.get_entity_merge_log_entry(999_999) is None
