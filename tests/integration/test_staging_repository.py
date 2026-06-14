from sqlalchemy import select

from domains.ingestion.models import RawData
from domains.staging.models import StagingDocument
from domains.staging.repository import get_pending_raw_records, upsert_staging_document
from domains.staging.schemas import StagingDocumentDTO

# ==========================================
# TESTES DO REPOSITÓRIO DA STAGING
# ==========================================


def test_get_pending_raw_records_encontra_novo_documento(use_test_db, db_session) -> None:
    """Garante que um dado na Ingestão que não existe na Staging seja retornado."""

    # 1. Cria um dado bruto na origem
    dado_bruto = RawData(
        description_id="doc-inédito", content_hash="hash-123", raw_title="Título Bruto", payload={"Data": "1990"}
    )
    db_session.add(dado_bruto)
    db_session.commit()

    # 2. Executa a busca
    pendentes = get_pending_raw_records(db_session)

    assert len(pendentes) == 1
    assert pendentes[0]["description_id"] == "doc-inédito"
    assert pendentes[0]["content_hash"] == "hash-123"


def test_get_pending_raw_records_ignora_documentos_sincronizados(use_test_db, db_session) -> None:
    """Garante que se os hashes baterem, o documento é ignorado."""

    dado_bruto = RawData(description_id="doc-sync", content_hash="hash-igual", payload={})
    # Simula que a Staging já processou este documento e guardou o mesmo hash
    dado_staging = StagingDocument(
        description_id="doc-sync", raw_content_hash="hash-igual", title="Título", raw_metadata={}
    )

    db_session.add_all([dado_bruto, dado_staging])
    db_session.commit()

    pendentes = get_pending_raw_records(db_session)

    # Não deve retornar nada, pois está tudo atualizado
    assert len(pendentes) == 0


def test_get_pending_raw_records_detecta_mudanca_de_hash(use_test_db, db_session) -> None:
    """Garante que se o conteúdo na prefeitura mudou (hash diferente), ele pede reprocessamento."""

    # Hash novo (Acabou de ser raspado)
    dado_bruto = RawData(description_id="doc-mudou", content_hash="hash-NOVO", payload={})
    # Hash antigo (Processado na semana passada)
    dado_staging = StagingDocument(
        description_id="doc-mudou", raw_content_hash="hash-VELHO", title="Título Antigo", raw_metadata={}
    )

    db_session.add_all([dado_bruto, dado_staging])
    db_session.commit()

    pendentes = get_pending_raw_records(db_session)

    # Tem que pegar, porque o hash mudou!
    assert len(pendentes) == 1
    assert pendentes[0]["description_id"] == "doc-mudou"


def test_upsert_staging_document_atualiza_registro_existente(use_test_db, db_session) -> None:
    """Testa o ON CONFLICT DO UPDATE substituindo os dados defasados."""

    # 1. Banco já possui uma versão antiga
    dado_antigo = StagingDocument(
        description_id="doc-update", raw_content_hash="hash-VELHO", title="Título Antigo", raw_metadata={}
    )
    db_session.add(dado_antigo)
    db_session.commit()

    # 2. Chega o DTO novo do Pydantic
    dto_novo = StagingDocumentDTO(
        description_id="doc-update", raw_content_hash="hash-NOVO", title="Título Novo Atualizado"
    )

    # 3. Faz o Upsert
    upsert_staging_document(db_session, dto_novo)

    # 4. Verifica se atualizou o banco (precisa do expire_all para limpar o cache)
    db_session.expire_all()
    doc_atualizado = db_session.execute(select(StagingDocument).filter_by(description_id="doc-update")).scalar_one()

    assert doc_atualizado.raw_content_hash == "hash-NOVO"
    assert doc_atualizado.title == "Título Novo Atualizado"
