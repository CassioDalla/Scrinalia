from sqlalchemy import select

from domains.archive.models import (
    ArchiveDocument,
    ArchiveReviewStatus,
)
from domains.archive.repository.document_repo import DocumentRepository

# ==========================================
# TESTES DE UPSERT E PIPELINE DE DADOS (ETL)
# ==========================================


def test_upsert_archive_document_insert_new(use_test_db, db_session, generate_archive_dto):
    """Cenário 1: Inserção de documento inédito vindo da Staging."""
    repo = DocumentRepository(db_session)
    dto_novo = generate_archive_dto(description_id="1", original_title="Inédito", staging_content_hash="hash_1")

    inseriu = repo.upsert_archive_document(dto_novo)
    db_session.commit()

    assert inseriu is True
    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="1")).scalar_one()
    assert doc_banco.original_title == "Inédito"


def test_upsert_archive_document_ignore_same_hash(use_test_db, db_session, generate_archive_dto):
    """Cenário 2: Carga Incremental. Documento com mesmo Hash deve ser ignorado."""
    repo = DocumentRepository(db_session)
    dto_original = generate_archive_dto(description_id="2", original_title="Original", staging_content_hash="hash_2")
    repo.upsert_archive_document(dto_original)
    db_session.commit()

    dto_repetido = generate_archive_dto(description_id="2", original_title="Falso", staging_content_hash="hash_2")
    inseriu_repetido = repo.upsert_archive_document(dto_repetido)
    db_session.commit()

    assert inseriu_repetido is False
    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="2")).scalar_one()
    assert doc_banco.original_title == "Original"


def test_upsert_archive_document_update_resets_ai(use_test_db, db_session, generate_archive_dto):
    """Cenário 3: CDC. Se o Hash mudou na Staging, atualiza os dados E apaga rastros de IA."""
    repo = DocumentRepository(db_session)
    dto_original = generate_archive_dto(
        description_id="3",
        original_title="Antigo",
        staging_content_hash="hash_3",
        execution_log={"ner_spacy_v1": "DONE"},
        review_status=ArchiveReviewStatus.NEEDS_REVIEW,
    )
    repo.upsert_archive_document(dto_original)
    db_session.commit()

    dto_novo = generate_archive_dto(
        description_id="3", original_title="Novo Título", staging_content_hash="hash_3_NOVO"
    )
    inseriu_novo = repo.upsert_archive_document(dto_novo)
    db_session.commit()

    assert inseriu_novo is True
    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="3")).scalar_one()
    assert doc_banco.original_title == "Novo Título"
    assert doc_banco.execution_log == {}  # O log foi resetado!
    assert doc_banco.review_status == ArchiveReviewStatus.PENDING_AI


def test_upsert_archive_document_blocked_by_human_approved(use_test_db, db_session, generate_archive_dto):
    """Cenário 4: Governança. Documento com status HUMAN_APPROVED bloqueia sobrescrita da ETL."""
    repo = DocumentRepository(db_session)
    dto_original = generate_archive_dto(
        description_id="4",
        original_title="Revisado Perfeito",
        staging_content_hash="hash_4",
        review_status=ArchiveReviewStatus.HUMAN_APPROVED,
    )
    repo.upsert_archive_document(dto_original)
    db_session.commit()

    dto_ataque = generate_archive_dto(
        description_id="4", original_title="Lixo da Staging", staging_content_hash="hash_4_NOVO"
    )
    inseriu_ataque = repo.upsert_archive_document(dto_ataque)
    db_session.commit()

    assert inseriu_ataque is False
    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="4")).scalar_one()
    assert doc_banco.original_title == "Revisado Perfeito"


# ==========================================
# TESTES DE IA
# ==========================================


def test_stamp_ai_execution(use_test_db, db_session, generate_archive_dto):
    """Testa se a coluna JSONB mutável salva o novo log garantindo o estado da ORM."""
    repo = DocumentRepository(db_session)
    dto = generate_archive_dto(description_id="27", execution_log={"migracao_base": "DONE"})
    repo.upsert_archive_document(dto)
    db_session.commit()

    repo.stamp_ai_execution("27", "ner_spacy_v1")
    db_session.commit()

    doc_banco = db_session.execute(select(ArchiveDocument).filter_by(description_id="27")).scalar_one()

    assert "migracao_base" in doc_banco.execution_log
    assert doc_banco.execution_log["ner_spacy_v1"] == "DONE"


# ==========================================
# TESTES DE LEITURA E CURADORIA
# ==========================================


def test_search_filters_by_term_and_paginates(use_test_db, db_session, generate_archive_dto):
    """Busca textual retorna apenas o matches e o total correto, respeitando a página."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="s1", original_title="Matadouro Municipal", staging_content_hash="h1")
    )
    repo.upsert_archive_document(
        generate_archive_dto(description_id="s2", original_title="Praça do Gaúcho", staging_content_hash="h2")
    )
    db_session.commit()

    docs, total = repo.search(term="Matadouro")
    assert total == 1
    assert docs[0].description_id == "s1"

    pagina, total_geral = repo.search(limit=1, offset=0)
    assert total_geral == 2
    assert len(pagina) == 1


def test_update_review_blinds_document_as_human_approved(use_test_db, db_session, generate_archive_dto):
    """A edição humana aplica os campos e marca o documento como HUMAN_APPROVED."""
    repo = DocumentRepository(db_session)
    repo.upsert_archive_document(
        generate_archive_dto(description_id="r1", original_title="Original", staging_content_hash="hr1")
    )
    db_session.commit()

    atualizado = repo.update_review("r1", {"final_title": "Título Revisado", "archivist_notes": "ok"})
    db_session.commit()

    assert atualizado is not None
    assert atualizado.review_status == ArchiveReviewStatus.HUMAN_APPROVED
    assert atualizado.final_title == "Título Revisado"


def test_update_review_returns_none_for_missing_document(use_test_db, db_session):
    repo = DocumentRepository(db_session)
    assert repo.update_review("nao-existe", {"final_title": "x"}) is None
