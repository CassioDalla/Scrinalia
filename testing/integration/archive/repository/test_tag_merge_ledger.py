"""
Integration tests of the tag-merge ledger: the undo has to be exact, not approximate.

The promise of the curation flow is that a merge a human approved can be reverted by a human.
These tests pin the two halves of that promise: the ledger records enough (the row, the
per-tag links, the spelling state) and the undo restores exactly that state — including the
links the merge created, which must disappear, and the ones that already existed, which must
not.
"""

import pytest
from sqlalchemy import delete, select

from scrinalia.domains.archive.exceptions import (
    MergeAlreadyUndoneError,
    MergeLogNotFoundError,
)
from scrinalia.domains.archive.models import (
    ArchiveDocument,
    ArchiveDocumentTag,
    ArchiveMacroCategory,
    ArchiveTag,
)
from scrinalia.domains.archive.repository.tag_repo import TagRepository
from scrinalia.domains.archive.schemas import (
    ArchiveTagDTO,
    MergeBatchEntry,
    MergePlan,
    SynonymCommand,
)


def _link(db_session, tag: ArchiveTag, document_id: str) -> None:
    db_session.add(ArchiveDocumentTag(description_id=document_id, tag_id=tag.tag_id))


def test_apply_merge_writes_one_ledger_row_per_absorbed_tag(use_test_db, db_session, generate_archive_doc):
    """The ledger keeps the snapshot, the exact links and who did it."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="rua")
    variant = ArchiveTag(name="ruas")
    db_session.add_all([canonical, variant])
    db_session.flush()

    docs = [generate_archive_doc(original_title=f"Doc {index}") for index in range(2)]
    for doc in docs:
        _link(db_session, variant, doc.description_id)
    db_session.flush()

    plan = repo.plan_merge(canonical.tag_id, [variant.tag_id])
    response = repo.apply_merge(plan, cluster_fingerprint="fp-1", changed_by="arquivista", note="mesmo conceito")
    db_session.flush()

    assert response.merge_ids == [entry.merge_id for entry in repo.list_merge_log()]

    log = repo.list_merge_log()
    assert repo.count_merge_log() == 1
    entry = log[0]
    assert entry.absorbed_name == "ruas"
    assert entry.canonical_name == "rua"
    assert entry.cluster_fingerprint == "fp-1"
    assert entry.changed_by == "arquivista"
    assert entry.note == "mesmo conceito"
    assert entry.document_count == 2
    assert entry.undone_at is None
    assert entry.synonym_created is True


def test_undo_merge_restores_the_tag_the_links_and_the_classification(use_test_db, db_session, generate_archive_doc):
    """Undo is lossless: id, name, category, confidence, AI log and links all come back."""
    repo = TagRepository(db_session)
    macro = ArchiveMacroCategory(name="Urbanismo", description="Obras e vias")
    db_session.add(macro)
    db_session.flush()

    canonical = ArchiveTag(name="rua")
    variant = ArchiveTag(
        name="ruas",
        macro_category_id=macro.category_id,
        ai_confidence_score=0.77,
        execution_log={"worker_macro_category_v1": "ok"},
    )
    db_session.add_all([canonical, variant])
    db_session.flush()
    restored_id = variant.tag_id

    doc = generate_archive_doc(original_title="Doc")
    _link(db_session, variant, doc.description_id)
    db_session.flush()

    merge_id = repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id]), changed_by="arquivista").merge_ids[
        0
    ]
    db_session.flush()
    assert db_session.get(ArchiveTag, restored_id) is None  # the tag is really gone

    entry = repo.undo_merge(merge_id, undone_by="arquivista")
    db_session.flush()

    restored = db_session.get(ArchiveTag, restored_id)
    assert restored is not None
    assert restored.name == "ruas"
    assert restored.macro_category_id == macro.category_id
    assert restored.ai_confidence_score == 0.77
    assert restored.execution_log == {"worker_macro_category_v1": "ok"}

    links = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert [(link.description_id, link.tag_id) for link in links] == [(doc.description_id, restored_id)]
    assert entry.undone_by == "arquivista"
    assert entry.undone_at is not None


def test_undo_merge_removes_only_the_links_the_merge_created(use_test_db, db_session, generate_archive_doc):
    """
    A document that already carried the canonical keeps it; the new links disappear.

    Restoring the tag without removing the links the merge created would leave the document
    with both spellings — not the state the archivist had before approving.
    """
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="rua")
    variant = ArchiveTag(name="ruas")
    db_session.add_all([canonical, variant])
    db_session.flush()

    only_variant = generate_archive_doc(original_title="Só a variante")
    both = generate_archive_doc(original_title="As duas")
    _link(db_session, variant, only_variant.description_id)
    _link(db_session, variant, both.description_id)
    _link(db_session, canonical, both.description_id)
    db_session.flush()

    merge_id = repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id])).merge_ids[0]
    db_session.flush()

    repo.undo_merge(merge_id)
    db_session.flush()

    links = db_session.scalars(select(ArchiveDocumentTag).order_by(ArchiveDocumentTag.description_id)).all()
    state = {(link.description_id, link.tag_id) for link in links}
    assert state == {
        (only_variant.description_id, variant.tag_id),
        (both.description_id, variant.tag_id),
        (both.description_id, canonical.tag_id),
    }


def test_undo_merge_moves_back_the_spellings_that_pointed_at_the_absorbed_tag(use_test_db, db_session):
    """A spelling absorbed by an earlier merge follows the tag when it is restored."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="prefeitura")
    variant = ArchiveTag(name="prefeitura de curitiba")
    db_session.add_all([canonical, variant])
    db_session.flush()
    restored_id = variant.tag_id

    repo.create_synonyms(
        [SynonymCommand(synonym_name="pmc", category="TAG", canonical_tag_id=variant.tag_id, canonical_entity_id=None)]
    )
    db_session.flush()

    merge_id = repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id])).merge_ids[0]
    db_session.flush()
    assert repo.get_synonyms_mapping(["pmc"]) == {"pmc": canonical.tag_id}

    repo.undo_merge(merge_id)
    db_session.flush()

    assert repo.get_synonyms_mapping(["pmc"]) == {"pmc": restored_id}
    # The spelling created for the absorbed name is gone, exactly as before the merge.
    assert repo.get_synonyms_mapping(["prefeitura de curitiba"]) == {}


def test_undo_merge_restores_a_spelling_that_already_pointed_somewhere_else(use_test_db, db_session):
    """When the spelling already existed, undo puts it back where it was instead of deleting it."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="rua")
    variant = ArchiveTag(name="ruas")
    other = ArchiveTag(name="logradouro")
    db_session.add_all([canonical, variant, other])
    db_session.flush()

    repo.create_synonyms(
        [SynonymCommand(synonym_name="ruas", category="TAG", canonical_tag_id=other.tag_id, canonical_entity_id=None)]
    )
    db_session.flush()

    merge_id = repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id])).merge_ids[0]
    db_session.flush()
    assert repo.get_synonyms_mapping(["ruas"]) == {"ruas": canonical.tag_id}

    repo.undo_merge(merge_id)
    db_session.flush()

    assert repo.get_synonyms_mapping(["ruas"]) == {"ruas": other.tag_id}


def test_undo_merge_is_single_shot(use_test_db, db_session):
    """The ledger keeps one reversal per merge; a second one is a conflict, not a silent no-op."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="casa")
    variant = ArchiveTag(name="casas")
    db_session.add_all([canonical, variant])
    db_session.flush()

    merge_id = repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id])).merge_ids[0]
    db_session.flush()
    repo.undo_merge(merge_id)

    with pytest.raises(MergeAlreadyUndoneError):
        repo.undo_merge(merge_id)


def test_undo_unknown_merge_raises_not_found(use_test_db, db_session):
    """An unknown ledger id is a 404, never an empty success."""
    with pytest.raises(MergeLogNotFoundError):
        TagRepository(db_session).undo_merge(999_999)


def test_undo_merge_tolerates_a_document_deleted_after_the_merge(use_test_db, db_session, generate_archive_doc):
    """A document that no longer exists must not make the undo impossible."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="lote")
    variant = ArchiveTag(name="lotes")
    db_session.add_all([canonical, variant])
    db_session.flush()

    doc = generate_archive_doc(original_title="Doc")
    _link(db_session, variant, doc.description_id)
    db_session.flush()

    merge_id = repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id])).merge_ids[0]
    db_session.flush()

    db_session.execute(delete(ArchiveDocument).where(ArchiveDocument.description_id == doc.description_id))
    db_session.flush()

    entry = repo.undo_merge(merge_id)
    db_session.flush()

    assert entry.document_count == 1  # what the ledger recorded
    assert db_session.get(ArchiveTag, variant.tag_id) is not None
    assert db_session.scalars(select(ArchiveDocumentTag).where(ArchiveDocumentTag.tag_id == variant.tag_id)).all() == []


def test_the_sequence_survives_an_undo(use_test_db, db_session):
    """Restoring an old id must not collide with the next tag the ingestion creates."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="igreja")
    variant = ArchiveTag(name="igrejas")
    db_session.add_all([canonical, variant])
    db_session.flush()

    merge_id = repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id])).merge_ids[0]
    db_session.flush()
    repo.undo_merge(merge_id)
    db_session.flush()

    new_ids = repo.get_or_create_tags(
        [
            ArchiveTagDTO(name="nova tag", macro_category_id=None),
            ArchiveTagDTO(name="outra tag", macro_category_id=None),
        ]
    )
    db_session.flush()

    assert len(set(new_ids)) == 2
    assert db_session.get(ArchiveTag, variant.tag_id) is not None


def test_apply_merge_batch_isolates_a_failing_cluster(use_test_db, db_session, generate_archive_doc):
    """One bad cluster is reported and rolled back; the good one is applied."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="obra")
    variant = ArchiveTag(name="obras")
    broken = ArchiveTag(name="obra.")  # will be absorbed into a canonical that does not exist
    db_session.add_all([canonical, variant, broken])
    db_session.flush()

    doc = generate_archive_doc(original_title="Doc")
    _link(db_session, variant, doc.description_id)
    db_session.flush()

    good_plan = repo.plan_merge(canonical.tag_id, [variant.tag_id])
    broken_plan = MergePlan(
        canonical_id=999_999,
        canonical_name="inexistente",
        ids_to_merge=[broken.tag_id],
        document_ids=[doc.description_id],
        documents_by_tag={broken.tag_id: [doc.description_id]},
    )

    result = repo.apply_merge_batch(
        [
            MergeBatchEntry(proposal_id=1, cluster_fingerprint="fp-good", plan=good_plan),
            MergeBatchEntry(proposal_id=2, cluster_fingerprint="fp-bad", plan=broken_plan),
        ],
        changed_by="arquivista",
    )

    assert [entry.proposal_id for entry in result.applied] == [1]
    assert [entry.proposal_id for entry in result.failed] == [2]
    assert result.applied[0].merge_ids
    assert result.applied[0].tags_deleted == 1
    assert result.failed[0].error

    db_session.flush()

    # The good cluster really landed, the bad one left nothing behind.
    assert db_session.get(ArchiveTag, variant.tag_id) is None
    assert db_session.get(ArchiveTag, broken.tag_id) is not None
    assert repo.count_merge_log() == 1


def test_merge_log_is_paginated_and_filtered(use_test_db, db_session):
    """The audit trail reports the total and filters by canonical, author and undone state."""
    repo = TagRepository(db_session)
    pairs = [("casa", "casas"), ("obra", "obras"), ("lote", "lotes")]
    merge_ids = []
    for index, (canonical_name, variant_name) in enumerate(pairs):
        canonical = ArchiveTag(name=canonical_name)
        variant = ArchiveTag(name=variant_name)
        db_session.add_all([canonical, variant])
        db_session.flush()
        author = "arquivista" if index < 2 else "outro"
        response = repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id]), changed_by=author)
        merge_ids.append(response.merge_ids[0])
    db_session.flush()

    assert repo.count_merge_log() == 3
    assert repo.count_merge_log(changed_by="arquivista") == 2
    assert repo.count_merge_log(canonical_id=999_999) == 0

    first_canonical = db_session.scalar(select(ArchiveTag).where(ArchiveTag.name == "casa"))
    assert repo.count_merge_log(canonical_id=first_canonical.tag_id) == 1

    assert len(repo.list_merge_log(limit=2)) == 2
    assert len(repo.list_merge_log(limit=2, offset=2)) == 1

    repo.undo_merge(merge_ids[0])
    db_session.flush()
    assert repo.count_merge_log(include_undone=False) == 2
    assert repo.count_merge_log(include_undone=True) == 3


def test_the_ledger_searches_both_sides_of_the_entry(db_session) -> None:
    """The archivist asking "where did this spelling go?" does not know which side it was on."""
    repo = TagRepository(db_session)
    for canonical_name, variant_name in (("avenida paulista", "av. paulista"), ("casa", "casas")):
        canonical = ArchiveTag(name=canonical_name)
        variant = ArchiveTag(name=variant_name)
        db_session.add_all([canonical, variant])
        db_session.flush()
        repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id]))
    db_session.flush()

    # The canonical side alone, the absorbed side alone, both sides of one entry (still one row), and
    # a term that is in neither.
    assert repo.count_merge_log(term="avenida") == 1
    assert repo.count_merge_log(term="av.") == 1
    assert repo.count_merge_log(term="paulista") == 1
    assert repo.count_merge_log(term="casas") == 1
    assert repo.count_merge_log(term="nada disso") == 0

    # The page and the count must agree on the filter, or the footer lies about the total.
    assert len(repo.list_merge_log(term="paulista")) == repo.count_merge_log(term="paulista")


def test_a_wildcard_in_the_ledger_search_is_a_character(db_session) -> None:
    """``%`` must not mean "everything": the ledger would answer the whole trail to a typo."""
    repo = TagRepository(db_session)
    for canonical_name, variant_name in (("casa", "casas"), ("cem por cento", "100%")):
        canonical = ArchiveTag(name=canonical_name)
        variant = ArchiveTag(name=variant_name)
        db_session.add_all([canonical, variant])
        db_session.flush()
        repo.apply_merge(repo.plan_merge(canonical.tag_id, [variant.tag_id]))
    db_session.flush()

    assert repo.count_merge_log(term="%") == 1
    assert repo.count_merge_log(term="_") == 0
