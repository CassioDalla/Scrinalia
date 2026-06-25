import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from domains.archive.models import ArchiveDocumentTag, ArchiveMacroCategory, ArchiveTag
from domains.archive.repository.tag_repo import TagRepository
from domains.archive.schemas.tag_schema import ArchiveTagDTO


def test_get_or_create_tags_new_and_lowercased(use_test_db, db_session):
    """Garante a criação de tags inéditas convertendo sempre para minúsculo."""
    repo = TagRepository(db_session)
    tags_dto = [ArchiveTagDTO(name=" ARQUIVAMENTO ", macro_category_id=None)]

    ids_gerados = repo.get_or_create_tags(tags_dto)
    db_session.commit()

    assert len(ids_gerados) == 1
    tag_db = db_session.execute(select(ArchiveTag).filter_by(tag_id=ids_gerados[0])).scalar_one()
    assert tag_db.name == "arquivamento"


def test_create_tag_com_macro_category_valida(use_test_db, db_session):
    """Garante que uma tag é criada e vinculada corretamente a uma categoria macro existente."""
    repo = TagRepository(db_session)
    macro = ArchiveMacroCategory(name="Administrativo", description="Documentos de RH e Gestão")
    db_session.add(macro)
    db_session.commit()

    tags_dto = [ArchiveTagDTO(name="ofício", macro_category_id=macro.category_id)]
    ids_gerados = repo.get_or_create_tags(tags_dto)
    db_session.commit()

    tag_db = db_session.get(ArchiveTag, ids_gerados[0])
    assert tag_db.name == "ofício"
    assert tag_db.macro_category_id == macro.category_id
    assert tag_db.macro_category.name == "Administrativo"


def test_falha_ao_criar_tag_com_macro_category_inexistente(use_test_db, db_session):
    """Garante que o banco de dados bloqueia a criação de tag com um ID de categoria fantasma."""
    repo = TagRepository(db_session)
    tags_dto = [ArchiveTagDTO(name="financeiro", macro_category_id=9999)]

    with pytest.raises(IntegrityError):
        repo.get_or_create_tags(tags_dto)
        db_session.commit()


def test_recupera_tag_existente_mantendo_macro_category(use_test_db, db_session):
    """Se a tag já existe, deve apenas retornar o ID mantendo a categoria intacta."""
    repo = TagRepository(db_session)
    macro = ArchiveMacroCategory(name="Financeiro")
    db_session.add(macro)
    db_session.commit()

    repo.get_or_create_tags([ArchiveTagDTO(name="recibo", macro_category_id=macro.category_id)])
    db_session.commit()

    ids_gerados = repo.get_or_create_tags([ArchiveTagDTO(name="RECIBO", macro_category_id=macro.category_id)])

    assert len(ids_gerados) == 1
    tag_db = db_session.get(ArchiveTag, ids_gerados[0])
    assert tag_db.macro_category_id == macro.category_id


def test_exclusao_de_macro_category_seta_fk_como_nulo(use_test_db, db_session):
    """Garante o comportamento 'SET NULL' quando a categoria pai é deletada."""
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
    """Testa o bulk insert com ON CONFLICT e a extração limpa."""
    repo = TagRepository(db_session)
    palavras_sujas = [" Curitiba ", "ofício", "", "  ", "Prefeitura"]

    repo.save_stopwords(palavras_sujas)
    db_session.commit()

    repo.save_stopwords(["ofício", "colombo"])
    db_session.commit()

    stopwords_db = repo.get_stopwords()

    assert "curitiba" in stopwords_db
    assert "prefeitura" in stopwords_db
    assert "" not in stopwords_db
    assert len(stopwords_db) == 4


def test_purge_tags_by_stopwords(use_test_db, db_session):
    """Garante a exclusão em massa das tags que dão 'match' na lista de stopwords."""
    repo = TagRepository(db_session)

    db_session.add_all([ArchiveTag(name="curitiba"), ArchiveTag(name="estado"), ArchiveTag(name="importante")])
    db_session.commit()

    stopwords = {"estado", "importante", "irrelevante"}

    apagadas = repo.purge_tags_by_stopwords(stopwords)
    db_session.commit()

    assert apagadas == 2
    tags_restantes = db_session.scalars(select(ArchiveTag.name)).all()
    assert "curitiba" in tags_restantes


def test_link_tags_to_document_com_duplicadas(use_test_db, db_session, generate_archive_doc):
    """
    Garante que o repositório vincula várias tags a 1 documento,
    ignora duplicatas na mesma lista (usando set) e respeita o ON CONFLICT.
    """
    repo = TagRepository(db_session)

    # 1. Setup
    doc = generate_archive_doc(description_id="doc_link_1", original_title="Documento Base")
    tag_a = ArchiveTag(name="tag_a")
    tag_b = ArchiveTag(name="tag_b")
    db_session.add_all([tag_a, tag_b])
    db_session.commit()

    # 2. Ação: Passamos a tag_a duas vezes na mesma requisição
    ids_tags = [tag_a.tag_id, tag_b.tag_id, tag_a.tag_id]
    repo.link_tags_to_document(description_id="doc_link_1", tag_ids=ids_tags)
    db_session.commit()

    # 3. Verificação 1: O set() limpou a duplicata da requisição
    qtd_vinculos = db_session.query(ArchiveDocumentTag).filter_by(description_id="doc_link_1").count()
    assert qtd_vinculos == 2

    # 4. Verificação 2: Idempotência (Rodar de novo não quebra o banco por causa do ON CONFLICT)
    repo.link_tags_to_document(description_id="doc_link_1", tag_ids=[tag_a.tag_id])
    db_session.commit()

    qtd_vinculos_final = db_session.query(ArchiveDocumentTag).filter_by(description_id="doc_link_1").count()
    assert qtd_vinculos_final == 2  # Continua 2!


def test_bulk_link_tags_otimizacao_worker(use_test_db, db_session, generate_archive_doc):
    """
    Testa a função de inserção massiva para Workers.
    Valida a conversão e deduplicação de dicionários e o bypass de conflitos no banco.
    """
    repo = TagRepository(db_session)

    # 1. Setup
    doc_1 = generate_archive_doc(description_id="doc_bulk_1", original_title="Lote 1")
    doc_2 = generate_archive_doc(description_id="doc_bulk_2", original_title="Lote 2")
    tag_x = ArchiveTag(name="tag_x")
    db_session.add_all([tag_x])
    db_session.commit()

    # 2. Ação: O Worker construiu uma lista com dicionários duplicados
    payload_worker = [
        {"description_id": "doc_bulk_1", "tag_id": tag_x.tag_id},
        {"description_id": "doc_bulk_2", "tag_id": tag_x.tag_id},
        {"description_id": "doc_bulk_1", "tag_id": tag_x.tag_id},  # 🚨 Dicionário 100% duplicado!
    ]

    repo.bulk_link_tags(payload_worker)
    db_session.commit()

    # 3. Verificação
    vinculos = db_session.scalars(select(ArchiveDocumentTag)).all()

    # O banco deve ter apenas 2 registros válidos. O Python deduplicou e o DB ignorou os erros.
    assert len(vinculos) == 2

    # Garante que os documentos certos receberam as tags
    docs_afetados = {v.description_id for v in vinculos}
    assert "doc_bulk_1" in docs_afetados
    assert "doc_bulk_2" in docs_afetados
