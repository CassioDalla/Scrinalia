import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from memoria_curitibana.domains.archive.exceptions import InvalidParam
from memoria_curitibana.domains.archive.models import (
    ArchiveDocumentTag,
    ArchiveMacroCategory,
    ArchiveTag,
)
from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository
from memoria_curitibana.domains.archive.schemas.command_schema import TagLinkCommand
from memoria_curitibana.domains.archive.schemas.tag_schema import ArchiveTagDTO


def test_get_or_create_tags_new_and_lowercased(use_test_db, db_session):
    """Guarantees the creation of brand-new tags, always converting to lowercase."""
    repo = TagRepository(db_session)
    tags_dto = [ArchiveTagDTO(name=" ARQUIVAMENTO ", macro_category_id=None)]

    generated_ids = repo.get_or_create_tags(tags_dto)
    db_session.commit()

    assert len(generated_ids) == 1
    tag_db = db_session.execute(select(ArchiveTag).filter_by(tag_id=generated_ids[0])).scalar_one()
    assert tag_db.name == "arquivamento"


def test_create_tag_with_valid_macro_category(use_test_db, db_session):
    """Guarantees that a tag is created and correctly linked to an existing macro category."""
    repo = TagRepository(db_session)
    macro = ArchiveMacroCategory(name="Administrativo", description="Documentos de RH e Gestão")
    db_session.add(macro)
    db_session.commit()

    tags_dto = [ArchiveTagDTO(name="ofício", macro_category_id=macro.category_id)]
    generated_ids = repo.get_or_create_tags(tags_dto)
    db_session.commit()

    tag_db = db_session.get(ArchiveTag, generated_ids[0])
    assert tag_db.name == "ofício"
    assert tag_db.macro_category_id == macro.category_id
    assert tag_db.macro_category.name == "Administrativo"


def test_fails_to_create_tag_with_missing_macro_category(use_test_db, db_session):
    """Guarantees that the database blocks the creation of a tag with a ghost category ID."""
    repo = TagRepository(db_session)
    tags_dto = [ArchiveTagDTO(name="financeiro", macro_category_id=9999)]

    with pytest.raises(IntegrityError):
        repo.get_or_create_tags(tags_dto)
        db_session.commit()


def test_retrieves_existing_tag_keeping_macro_category(use_test_db, db_session):
    """If the tag already exists, it must only return the ID while keeping the category intact."""
    repo = TagRepository(db_session)
    macro = ArchiveMacroCategory(name="Financeiro")
    db_session.add(macro)
    db_session.commit()

    repo.get_or_create_tags([ArchiveTagDTO(name="recibo", macro_category_id=macro.category_id)])
    db_session.commit()

    generated_ids = repo.get_or_create_tags([ArchiveTagDTO(name="RECIBO", macro_category_id=macro.category_id)])

    assert len(generated_ids) == 1
    tag_db = db_session.get(ArchiveTag, generated_ids[0])
    assert tag_db.macro_category_id == macro.category_id


def test_macro_category_deletion_sets_fk_to_null(use_test_db, db_session):
    """Guarantees the 'SET NULL' behavior when the parent category is deleted."""
    macro = ArchiveMacroCategory(name="Projetos Especiais")
    db_session.add(macro)
    db_session.commit()

    tag = ArchiveTag(name="planta_baixa", macro_category_id=macro.category_id)
    db_session.add(tag)
    db_session.commit()

    db_session.delete(macro)
    db_session.commit()

    db_session.refresh(tag)
    assert tag.macro_category_id is None
    assert tag.name == "planta_baixa"


def test_save_and_get_stopwords(use_test_db, db_session):
    """Tests the bulk insert with ON CONFLICT and the clean extraction."""
    repo = TagRepository(db_session)
    dirty_words = [" Curitiba ", "ofício", "", "  ", "Prefeitura"]

    repo.save_stopwords(dirty_words)
    db_session.commit()

    repo.save_stopwords(["ofício", "colombo"])
    db_session.commit()

    stopwords_db = repo.get_stopwords()

    assert "curitiba" in stopwords_db
    assert "prefeitura" in stopwords_db
    assert "" not in stopwords_db
    assert len(stopwords_db) == 4


def test_purge_tags_by_stopwords(use_test_db, db_session):
    """Guarantees the bulk deletion of tags that 'match' the stopword list."""
    repo = TagRepository(db_session)

    db_session.add_all([ArchiveTag(name="curitiba"), ArchiveTag(name="estado"), ArchiveTag(name="importante")])
    db_session.commit()

    stopwords = {"estado", "importante", "irrelevante"}

    deleted = repo.purge_tags_by_stopwords(stopwords)
    db_session.commit()

    assert deleted == 2
    remaining_tags = db_session.scalars(select(ArchiveTag.name)).all()
    assert "curitiba" in remaining_tags


def test_link_tags_to_document_with_duplicates(use_test_db, db_session, generate_archive_doc):
    """
    Guarantees that the repository links several tags to 1 document,
    ignores duplicates in the same list (using a set) and respects the ON CONFLICT.
    """
    repo = TagRepository(db_session)

    # 1. Setup
    generate_archive_doc(description_id="doc_link_1", original_title="Documento Base")
    tag_a = ArchiveTag(name="tag_a")
    tag_b = ArchiveTag(name="tag_b")
    db_session.add_all([tag_a, tag_b])
    db_session.commit()

    # 2. Action: We pass tag_a twice in the same request
    tag_ids = [tag_a.tag_id, tag_b.tag_id, tag_a.tag_id]
    repo.link_tags_to_document(description_id="doc_link_1", tag_ids=tag_ids)
    db_session.commit()

    # 3. Check 1: The set() cleaned the duplicate from the request
    link_count = db_session.query(ArchiveDocumentTag).filter_by(description_id="doc_link_1").count()
    assert link_count == 2

    # 4. Check 2: Idempotency (Running it again does not break the database thanks to ON CONFLICT)
    repo.link_tags_to_document(description_id="doc_link_1", tag_ids=[tag_a.tag_id])
    db_session.commit()

    final_link_count = db_session.query(ArchiveDocumentTag).filter_by(description_id="doc_link_1").count()
    assert final_link_count == 2  # Still 2!


def test_bulk_link_tags_worker_optimization(use_test_db, db_session, generate_archive_doc):
    """
    Tests the bulk insert function for Workers.
    Validates the conversion and deduplication of dictionaries and the bypass of database conflicts.
    """
    repo = TagRepository(db_session)

    # 1. Setup
    generate_archive_doc(description_id="doc_bulk_1", original_title="Lote 1")
    generate_archive_doc(description_id="doc_bulk_2", original_title="Lote 2")
    tag_x = ArchiveTag(name="tag_x")
    db_session.add_all([tag_x])
    db_session.commit()

    # 2. Action: The Worker built a list with duplicate dictionaries
    worker_payload = [
        TagLinkCommand(description_id="doc_bulk_1", tag_id=tag_x.tag_id),
        TagLinkCommand(description_id="doc_bulk_2", tag_id=tag_x.tag_id),
        TagLinkCommand(description_id="doc_bulk_1", tag_id=tag_x.tag_id),  # 🚨 100% duplicated command!
    ]

    repo.bulk_link_tags(worker_payload)
    db_session.commit()

    # 3. Check
    links = db_session.scalars(select(ArchiveDocumentTag)).all()

    # The database must have only 2 valid records. Python deduplicated and the DB ignored the errors.
    assert len(links) == 2

    # Guarantees that the right documents received the tags
    affected_docs = {v.description_id for v in links}
    assert "doc_bulk_1" in affected_docs
    assert "doc_bulk_2" in affected_docs


# ==========================================
# MACRO CATEGORY CRUD (SUBJECT AXIS)
# ==========================================


def test_create_macro_category_returns_the_persisted_entity(use_test_db, db_session):
    repo = TagRepository(db_session)

    created = repo.create_macro_category(name="Urbanismo", description="Obras e vias")

    assert created.category_id is not None
    assert created.name == "Urbanismo"
    assert created.description == "Obras e vias"
    assert created.is_active is True
    assert db_session.get(ArchiveMacroCategory, created.category_id).name == "Urbanismo"


def test_update_macro_category_renames_and_deactivates(use_test_db, db_session):
    repo = TagRepository(db_session)
    created = repo.create_macro_category(name="Saúde", description=None)

    updated = repo.update_macro_category(created.category_id, {"name": "Saúde Pública", "is_active": False})

    assert updated is not None
    assert updated.name == "Saúde Pública"
    assert updated.is_active is False


def test_update_macro_category_returns_none_when_missing(use_test_db, db_session):
    repo = TagRepository(db_session)

    assert repo.update_macro_category(9999, {"name": "Fantasma"}) is None


def test_get_macro_categories_filters_inactive(use_test_db, db_session):
    repo = TagRepository(db_session)
    repo.create_macro_category(name="Ativa", description=None)
    inactive = repo.create_macro_category(name="Inativa", description=None)
    repo.update_macro_category(inactive.category_id, {"is_active": False})
    db_session.commit()

    assert {c.name for c in repo.get_macro_categories()} == {"Ativa", "Inativa"}
    assert [c.name for c in repo.get_macro_categories(only_active=True)] == ["Ativa"]


def test_get_active_macro_categories_builds_classifier_labels(use_test_db, db_session):
    """
    The classifier reads bare names, and inactive categories are excluded.

    Regression: the label used to be ``"Name: description"``. Appending the description
    made mDeBERTa progressively lose the entailment until it collapsed every tag onto a
    single category, with high confidence on the wrong answer — so a curator who filled
    the description made classification worse. The description stays as documentation.
    """
    repo = TagRepository(db_session)
    urban = repo.create_macro_category(name="Urbanismo", description="Obras e vias")
    health = repo.create_macro_category(name="Saúde", description=None)
    dead = repo.create_macro_category(name="Descontinuada", description="não deve entrar")
    repo.update_macro_category(dead.category_id, {"is_active": False})
    db_session.commit()

    labels = repo.get_active_macro_categories()

    assert labels == {"Urbanismo": urban.category_id, "Saúde": health.category_id}
    assert all(":" not in label for label in labels)
    assert "Obras e vias" not in labels


# ==========================================
# MERGE SUGGESTIONS (plural + trigram, never a merge)
# ==========================================


def test_merge_suggestions_group_plural_and_singular(db_session, generate_archive_doc):
    from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository

    plural = ArchiveTag(name="livros")
    singular = ArchiveTag(name="livro")
    db_session.add_all([plural, singular])
    db_session.flush()
    doc = generate_archive_doc(original_title="Doc")
    db_session.add_all(
        [
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=plural.tag_id),
            ArchiveDocumentTag(description_id=doc.description_id, tag_id=singular.tag_id),
        ]
    )
    db_session.flush()

    suggestions = TagRepository(db_session).find_merge_suggestions(threshold=0.99)

    cluster = next(s for s in suggestions if "livros" in [m.name for m in s.members])
    assert {member.name for member in cluster.members} == {"livro", "livros"}
    assert cluster.reason == "PLURAL"
    # Both tags hang from the same document, so the canonical keeps the most used spelling.
    assert cluster.canonical_name in {"livro", "livros"}
    assert cluster.total_documents == 1


def test_merge_suggestions_canonical_is_the_most_used_spelling(db_session, generate_archive_doc):
    from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository

    popular = ArchiveTag(name="casas")
    rare = ArchiveTag(name="casa")
    db_session.add_all([popular, rare])
    db_session.flush()
    for index in range(3):
        doc = generate_archive_doc(original_title=f"Doc {index}")
        db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=popular.tag_id))
    doc = generate_archive_doc(original_title="Doc raro")
    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=rare.tag_id))
    db_session.flush()

    suggestions = TagRepository(db_session).find_merge_suggestions(threshold=0.99)

    cluster = next(s for s in suggestions if "casa" in [m.name for m in s.members])
    assert cluster.canonical_name == "casas"
    assert cluster.total_documents == 4


def test_merge_suggestions_never_merge_anything(db_session, generate_archive_doc):
    from sqlalchemy import func, select

    from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository

    db_session.add_all([ArchiveTag(name="obras"), ArchiveTag(name="obra")])
    db_session.flush()

    TagRepository(db_session).find_merge_suggestions()

    assert db_session.scalar(select(func.count()).select_from(ArchiveTag)) == 2


def test_merge_suggestions_respect_the_limit(db_session):
    from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository

    for singular, plural in (("livro", "livros"), ("casa", "casas"), ("carro", "carros")):
        db_session.add_all([ArchiveTag(name=singular), ArchiveTag(name=plural)])
    db_session.flush()

    assert len(TagRepository(db_session).find_merge_suggestions(limit=2)) == 2


def test_merge_suggestions_of_an_empty_catalog_are_empty(db_session):
    from memoria_curitibana.domains.archive.repository.tag_repo import TagRepository

    assert TagRepository(db_session).find_merge_suggestions() == []


# ==========================================
# SYNONYM WRITES (the merge ledger of spellings)
# ==========================================


def test_create_synonyms_repoints_an_existing_mapping(use_test_db, db_session):
    """
    Writing the same spelling again must move it, not be silently ignored.

    ``on_conflict_do_nothing`` kept the first canonical forever, so correcting the target of
    an already-absorbed spelling was impossible — the write looked successful and changed
    nothing.
    """
    from memoria_curitibana.domains.archive.schemas import SynonymCommand

    repo = TagRepository(db_session)
    first = ArchiveTag(name="foto")
    second = ArchiveTag(name="imagem")
    db_session.add_all([first, second])
    db_session.commit()

    repo.create_synonyms(
        [SynonymCommand(synonym_name="fotu", category="TAG", canonical_tag_id=first.tag_id, canonical_entity_id=None)]
    )
    repo.create_synonyms(
        [SynonymCommand(synonym_name="fotu", category="TAG", canonical_tag_id=second.tag_id, canonical_entity_id=None)]
    )
    db_session.flush()

    assert repo.get_synonyms_mapping(["fotu"]) == {"fotu": second.tag_id}


# ==========================================
# MERGE PROPOSALS (persisted evidence + human decision)
# ==========================================


def _suggestion(canonical: ArchiveTag, members: list[ArchiveTag], reason: str = "PLURAL"):
    from memoria_curitibana.domains.archive.schemas import TagMergeMember, TagMergeSuggestion

    ordered = [canonical, *members]
    return TagMergeSuggestion(
        canonical_id=canonical.tag_id,
        canonical_name=canonical.name,
        total_documents=0,
        reason=reason,
        members=[TagMergeMember(tag_id=tag.tag_id, name=tag.name, document_count=0) for tag in ordered],
    )


def test_upsert_merge_proposals_registers_the_cluster_with_evidence(use_test_db, db_session):
    """The suggestion is persisted with its members and its own identity, pending decision."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="casa")
    variant = ArchiveTag(name="casas")
    db_session.add_all([canonical, variant])
    db_session.commit()

    assert repo.upsert_merge_proposals([_suggestion(canonical, [variant])]) == 1

    page = repo.list_merge_proposals()
    assert repo.count_merge_proposals() == 1
    assert len(page) == 1

    proposal = page[0]
    assert proposal.status == "SUGGESTED"
    assert proposal.canonical_name == "casa"
    assert proposal.reason == "PLURAL"
    assert [member.name for member in proposal.members] == ["casa", "casas"]
    assert proposal.fingerprint
    assert proposal.decided_by is None


def test_upsert_merge_proposals_never_overwrites_a_human_decision(use_test_db, db_session):
    """
    Re-running the suggester must not resurrect a rejected cluster.

    Without the guard on the conflict target, the archivist would re-review the same
    hundreds of proposals on every run.
    """
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="rua 13 de maio")
    variant = ArchiveTag(name="rua 23 de maio")
    db_session.add_all([canonical, variant])
    db_session.commit()
    suggestion = _suggestion(canonical, [variant], reason="TRIGRAM")

    assert repo.upsert_merge_proposals([suggestion]) == 1
    proposal_id = repo.list_merge_proposals()[0].proposal_id

    decided = repo.decide_merge_proposal(proposal_id, "REJECTED", "arquivista", "são ruas diferentes")
    assert decided is not None
    assert decided.status == "REJECTED"
    assert decided.decided_by == "arquivista"
    assert decided.decided_at is not None

    assert repo.upsert_merge_proposals([suggestion]) == 0
    assert repo.get_merge_proposal(proposal_id).status == "REJECTED"


def test_merge_proposals_flag_the_number_bearing_members(use_test_db, db_session):
    """The measured bad merges (rua <- rua 7) arrive flagged for the curator."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="rua")
    variant = ArchiveTag(name="rua 7")
    db_session.add_all([canonical, variant])
    db_session.commit()

    repo.upsert_merge_proposals([_suggestion(canonical, [variant], reason="TRIGRAM")])

    assert "MEMBER_WITH_DIGITS" in repo.list_merge_proposals()[0].review_flags


def test_merge_proposals_flag_a_classification_that_would_be_lost(use_test_db, db_session):
    """An orphan canonical absorbing a classified tag would silently drop the classification."""
    repo = TagRepository(db_session)
    macro = ArchiveMacroCategory(name="Urbanismo", description="Obras e vias")
    db_session.add(macro)
    db_session.flush()

    canonical = ArchiveTag(name="obra")
    variant = ArchiveTag(name="obras", macro_category_id=macro.category_id)
    db_session.add_all([canonical, variant])
    db_session.commit()

    repo.upsert_merge_proposals([_suggestion(canonical, [variant])])

    assert "CATEGORY_WOULD_BE_LOST" in repo.list_merge_proposals()[0].review_flags


def test_merge_proposals_are_paginated_with_a_total(use_test_db, db_session):
    """The listing reports how many clusters match, not only the page (the old route hid them)."""
    repo = TagRepository(db_session)
    suggestions = []
    for singular, plural in (("livro", "livros"), ("casa", "casas"), ("carro", "carros")):
        canonical = ArchiveTag(name=singular)
        variant = ArchiveTag(name=plural)
        db_session.add_all([canonical, variant])
        db_session.flush()
        suggestions.append(_suggestion(canonical, [variant]))

    repo.upsert_merge_proposals(suggestions)

    first_page = repo.list_merge_proposals(limit=2)
    assert repo.count_merge_proposals() == 3
    assert len(first_page) == 2
    assert len(repo.list_merge_proposals(limit=2, offset=2)) == 1


def test_merge_proposals_put_pending_work_first(use_test_db, db_session):
    """A decided cluster must not bury the ones still waiting for the archivist."""
    repo = TagRepository(db_session)
    decided_tag = ArchiveTag(name="igreja")
    decided_variant = ArchiveTag(name="igrejas")
    pending_tag = ArchiveTag(name="lote")
    pending_variant = ArchiveTag(name="lotes")
    db_session.add_all([decided_tag, decided_variant, pending_tag, pending_variant])
    db_session.commit()

    repo.upsert_merge_proposals(
        [_suggestion(decided_tag, [decided_variant]), _suggestion(pending_tag, [pending_variant])]
    )
    decided_id = next(
        proposal.proposal_id for proposal in repo.list_merge_proposals() if proposal.canonical_name == "igreja"
    )
    repo.decide_merge_proposal(decided_id, "APPROVED", "arquivista", None)

    first = repo.list_merge_proposals()[0]
    assert first.canonical_name == "lote"
    assert first.status == "SUGGESTED"


# ==========================================
# MERGE PLAN (single definition of the write)
# ==========================================


def test_plan_merge_describes_the_impact_without_writing(use_test_db, db_session, generate_archive_doc):
    """The dry-run is read-only: no tag, link or synonym changes."""
    from sqlalchemy import func

    from memoria_curitibana.domains.archive.models import DomainSynonyms

    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="rua")
    variant = ArchiveTag(name="ruas")
    db_session.add_all([canonical, variant])
    db_session.flush()

    doc = generate_archive_doc(original_title="Doc")
    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=variant.tag_id))
    db_session.flush()

    plan = repo.plan_merge(canonical.tag_id, [variant.tag_id])

    assert plan.canonical_name == "rua"
    assert plan.ids_to_merge == [variant.tag_id]
    assert plan.documents_updated == 1
    assert plan.links_rewritten == 1
    assert plan.synonym_names == ["ruas"]
    assert [member.name for member in plan.impacted] == ["ruas"]

    # Nothing was written.
    assert db_session.scalar(select(func.count()).select_from(ArchiveTag)) == 2
    assert db_session.scalar(select(func.count()).select_from(DomainSynonyms)) == 0
    assert db_session.scalar(select(func.count()).select_from(ArchiveDocumentTag)) == 1


def test_plan_merge_raises_when_the_canonical_does_not_exist(use_test_db, db_session):
    """A missing canonical is a domain error, not an empty plan."""
    with pytest.raises(InvalidParam, match="não existe no acervo"):
        TagRepository(db_session).plan_merge(999_999, [1])


def test_apply_merge_executes_exactly_the_plan(use_test_db, db_session, generate_archive_doc):
    """Applying the plan moves the links, absorbs the spellings and deletes the tags."""
    repo = TagRepository(db_session)
    canonical = ArchiveTag(name="prefeitura")
    variant = ArchiveTag(name="prefeiruta")
    db_session.add_all([canonical, variant])
    db_session.flush()

    doc = generate_archive_doc(original_title="Doc")
    db_session.add(ArchiveDocumentTag(description_id=doc.description_id, tag_id=variant.tag_id))
    db_session.flush()

    plan = repo.plan_merge(canonical.tag_id, [variant.tag_id])
    response = repo.apply_merge(plan)
    db_session.flush()

    assert response.documents_updated == 1
    assert response.tags_deleted == 1
    assert repo.get_synonyms_mapping(["prefeiruta"]) == {"prefeiruta": canonical.tag_id}
    links = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert [(link.description_id, link.tag_id) for link in links] == [(doc.description_id, canonical.tag_id)]
    assert db_session.scalars(select(ArchiveTag.name)).all() == ["prefeitura"]
