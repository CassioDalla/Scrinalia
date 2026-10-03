import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from memoria_curitibana.domains.archive.models import ArchiveDocumentTag, ArchiveMacroCategory, ArchiveTag
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
    """The label carries the description so the zero-shot model can disambiguate, and inactive ones are out."""
    repo = TagRepository(db_session)
    urban = repo.create_macro_category(name="Urbanismo", description="Obras e vias")
    health = repo.create_macro_category(name="Saúde", description=None)
    dead = repo.create_macro_category(name="Descontinuada", description="não deve entrar")
    repo.update_macro_category(dead.category_id, {"is_active": False})
    db_session.commit()

    assert repo.get_active_macro_categories() == {
        "Urbanismo: Obras e vias": urban.category_id,
        "Saúde": health.category_id,
    }
