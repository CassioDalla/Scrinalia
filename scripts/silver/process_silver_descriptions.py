from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.crud import silver_crud
from core.database import get_db
from core.logger import logger
from core.schemas.SilverSchema import SilverDescription


def run_silver_pipeline(db_session: Session) -> None:
    """
    Orquestra o fluxo Bronze -> Schema Pydantic -> Model SQLAlchemy -> Banco.
    """
    logger.info("🔍 Verificando documentos pendentes na Camada Bronze...")
    pending_records = silver_crud.get_pending_bronze_records(db_session)

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
            clean_record = SilverDescription.model_validate(raw_data)
            silver_crud.upsert_silver_record(db_session, clean_record)

            sucesso += 1
            if i % 50 == 0:
                logger.info(f"⏳ Processados {i}/{total}...")

        except ValidationError as e:
            # Se o Pydantic recusar o dado, logamos o erro, mas não matamos o loop
            falhas += 1
            logger.error(f"❌ Pydantic rejeitou o doc {doc_id}: {e.error_count()} erros encontrados.")
            logger.debug(f"Detalhes do erro Pydantic: {e.errors()}")

        except Exception as e:
            falhas += 1
            logger.error(f"💥 Erro fatal ao salvar o doc {doc_id} no banco: {str(e)}")
            db_session.rollback()  # Limpa a transação atual para o próximo não quebrar
            continue

    try:
        db_session.commit()
        logger.info(f"🎯 Pipeline Silver Concluído! Sucessos: {sucesso} | Falhas: {falhas}")
    except Exception as e:
        db_session.rollback()
        logger.critical(f"🔥 Erro crítico ao fazer o commit final: {str(e)}")


if __name__ == "__main__":
    with get_db() as db:
        db_session: Session = db
        run_silver_pipeline(db_session)
