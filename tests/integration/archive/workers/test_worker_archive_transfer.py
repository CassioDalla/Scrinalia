from sqlalchemy import select

from domains.archive.models import ArchiveDocument, ArchiveDocumentTag, ArchiveTag
from domains.archive.workers import worker_archive_transfer
from domains.staging.models import StagingDocument


def test_integration_worker_etl_end_to_end(use_test_db, db_session):
    """
    Testa o pipeline completo de Ingestão (End-to-End).
    Garante que os dados saem da Staging, passam pelas validações,
    extração de tags e chegam íntegros nas tabelas Fato (Archive).
    """
    # 1. SETUP: Criamos dados sujos na Staging (simulando a realidade)
    doc1 = StagingDocument(
        description_id="br_pr_123",
        title="  Ata da Reunião  ",  # Título com espaços extras
        raw_content_hash="hash_novo_1",
        scope_content="Conteúdo válido",
        indexing_points="Urbanismo, Obras, Lixo, ",  # Tem tags úteis e lixo
    )
    doc2 = StagingDocument(
        description_id="br_pr_456",
        title="Decreto Municipal",
        raw_content_hash="hash_novo_2",
        scope_content="Outro conteúdo",
        indexing_points="Obras, Prefeito",  # "Obras" repetido no lote para testar o Bulk Insert deduplicado
    )

    db_session.add_all([doc1, doc2])

    # Vamos aproveitar e cadastrar 'Lixo' como uma stopword para ver a mágica a acontecer
    from domains.archive.repository.tag_repo import TagRepository

    TagRepository(db_session).save_stopwords(["lixo"])
    db_session.commit()

    # 2. AÇÃO: Rodamos o orquestrador no banco real
    worker_archive_transfer.execute(db_session)

    # 3. VALIDAÇÃO DOS DOCUMENTOS
    docs_migrados = db_session.scalars(select(ArchiveDocument).order_by(ArchiveDocument.description_id)).all()
    assert len(docs_migrados) == 2

    # Validando se o título foi parar ao lugar certo (mesmo com os espaços sujos, a DTO deve ter passado)
    doc_1_banco = next(d for d in docs_migrados if d.description_id == "br_pr_123")
    assert doc_1_banco.original_title == "  Ata da Reunião  "
    assert doc_1_banco.staging_content_hash == "hash_novo_1"

    # 4. VALIDAÇÃO DAS TAGS (Criação e Limpeza)
    tags_geradas = db_session.scalars(select(ArchiveTag.name)).all()

    # "Lixo" deve ter sumido. "Obras" deve ter sido deduplicado. Sobram: urbanismo, obras, prefeito
    assert len(tags_geradas) == 3
    assert "urbanismo" in tags_geradas
    assert "obras" in tags_geradas
    assert "prefeito" in tags_geradas
    assert "lixo" not in tags_geradas

    # 5. VALIDAÇÃO DOS VÍNCULOS N:N (Otimização do Bulk Insert funcionou?)
    vinculos = db_session.scalars(select(ArchiveDocumentTag)).all()
    assert len(vinculos) == 4  # 2 do primeiro doc + 2 do segundo doc


def test_integration_worker_etl_ignora_documentos_repetidos(use_test_db, db_session):
    """
    Testa a Idempotência no banco de dados real.
    Garante que se o Worker rodar duas vezes, não duplica dados nem estoura erros.
    """
    # 1. SETUP: Documento na Staging
    doc = StagingDocument(
        description_id="doc_idempotente", title="Fixo", raw_content_hash="hash_imutavel", indexing_points="Tag_A"
    )
    db_session.add(doc)
    db_session.commit()

    # 2. AÇÃO 1: Roda a primeira vez (Carga Inicial)
    worker_archive_transfer.execute(db_session)

    qtd_docs_1 = db_session.query(ArchiveDocument).count()
    qtd_tags_1 = db_session.query(ArchiveTag).count()
    qtd_vinculos_1 = db_session.query(ArchiveDocumentTag).count()

    # 3. AÇÃO 2: Roda a segunda vez (Reprocessamento)
    worker_archive_transfer.execute(db_session)

    qtd_docs_2 = db_session.query(ArchiveDocument).count()
    qtd_tags_2 = db_session.query(ArchiveTag).count()
    qtd_vinculos_2 = db_session.query(ArchiveDocumentTag).count()

    # 4. VALIDAÇÃO: O banco deve estar exatamente igual, nada pode ter sido criado na segunda passada
    assert qtd_docs_1 == 1 and qtd_docs_2 == 1
    assert qtd_tags_1 == 1 and qtd_tags_2 == 1
    assert qtd_vinculos_1 == 1 and qtd_vinculos_2 == 1
