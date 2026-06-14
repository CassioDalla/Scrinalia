from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.database import get_db
from core.logger import logger
from domains.staging import repository
from domains.staging.schemas import StagingDocumentDTO


def run_silver_pipeline(db_session: Session) -> None:
    """
    Orquestra o pipeline de transformação (Transform/Load) da camada Staging.

    Executa os seguintes passos atômicos:
    1. Busca os documentos brutos (RawData) pendentes ou desatualizados.
    2. Valida, higieniza e tipa os dados usando o Schema do Pydantic.
    3. Atualiza a base relacional estruturada usando upserts no repositório.
    4. Aplica Savepoints (begin_nested) para garantir que documentos defeituosos
       sejam ignorados sem abortar a transação do lote inteiro.

    Args:
        db_session (Session): Sessão ativa do SQLAlchemy.
    """
    logger.info("🔍 Verificando documentos pendentes na Camada Bronze...")
    pending_records = repository.get_pending_raw_records(db_session)

    total = len(pending_records)
    if total == 0:
        logger.success("✅ Nenhum documento novo ou alterado encontrado.")
        return

    logger.info(f"🚀 Iniciando processamento de {total} documentos...")

    sucesso = 0
    falhas = 0

    for i, raw_data in enumerate(pending_records, start=1):
        doc_id = raw_data.get("description_id", "DESCONHECIDO")
        try:
            # Validação e Limpeza (Pydantic - Em Memória)
            clean_record = StagingDocumentDTO.model_validate(raw_data)

            # Persistência
            # O savepoint garante que se um erro de SQL ocorrer aqui,
            # apenas este 'upsert' é desfeito, protegendo o resto do lote.
            with db_session.begin_nested():
                repository.upsert_staging_document(db_session, clean_record)

            sucesso += 1
            if i % 50 == 0:
                logger.info(f"⏳ Processados {i}/{total}...")

        except ValidationError as e:
            # Se o Pydantic recusar o dado
            falhas += 1
            logger.error(f"❌ Pydantic rejeitou o doc {doc_id}: {e.error_count()} erros encontrados.")
            logger.debug(f"Detalhes do erro Pydantic: {e.errors()}")

        except Exception as e:
            # Erros de infra/banco de dados (Constraint violada, tipagem de banco, etc)
            falhas += 1
            logger.error(f"💥 Erro fatal ao salvar o doc {doc_id} no banco: {str(e)}")
            continue

    try:
        db_session.commit()
        logger.info(f"🎯 Pipeline Silver Concluído! Sucessos: {sucesso} | Falhas: {falhas}")
    except Exception as e:
        db_session.rollback()
        logger.critical(f"🔥 Erro crítico ao fazer o commit final: {str(e)}")


if __name__ == "__main__":
    with get_db() as db:
        run_silver_pipeline(db)
