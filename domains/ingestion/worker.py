from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from core.database import get_db
from core.logger import logger
from domains.ingestion import repository
from domains.ingestion.models import ScrapeStatus
from domains.ingestion.ports import (
    AdapterFatalError,
    AdapterNetworkError,
    AdapterNotFoundError,
    IDetailAdapter,
    IDiscoveryAdapter,
)

MAX_RETRIES = 3


def run_discovery_job(db_session: Session, adapter: IDiscoveryAdapter, max_pages: int | None = None):
    """
    Orquestra a fase de descoberta da Ingestão, buscando novos IDs na fonte de dados.

    Utiliza um adaptador de descoberta (IDiscoveryAdapter) para iterar sobre a
    fonte (páginas web, planilhas, APIs) e insere os identificadores inéditos
    na Fila de Processamento em lotes (bulk insert).

    Args:
        db_session (Session): Sessão ativa do SQLAlchemy.
        adapter (IDiscoveryAdapter): Instância do adaptador responsável por buscar os IDs.
        max_pages (int | None, opcional): Limite de iterações/páginas a serem processadas.
    """

    logger.info("🚀 Iniciando a descoberta de IDs no catálogo...")

    total_inserted = 0
    for batch_ids in adapter.fetch_new_ids(max_pages=max_pages):
        inserted_count = repository.add_in_bulk(db_session, batch_ids)
        total_inserted += inserted_count

        if inserted_count > 0:
            logger.success(f"🔥 +{inserted_count} novos documentos na fila.")

    if total_inserted == 0:
        logger.warning("Nenhum ID inédito foi encontrado nesta execução.")


def run_detail_scraping_job(
    db_session: Session,
    adapter: IDetailAdapter,
    force_retry_fatal: bool = False,
    ignore_sliding_window: bool = False,
    audit_ttl_days: int | None = None,
):
    """
    Orquestra o consumo da fila e a extração dos dados brutos (RawData).

    Aplica as regras de negócio de tempo de vida (TTL) e janelas temporais
    para selecionar quais documentos devem ser processados. Para cada item,
    solicita ao adaptador a extração dos metadados e atualiza o estado
    do processamento, aplicando contagem de falhas (retries) em caso de instabilidade.

    Args:
        db_session (Session): Sessão ativa do SQLAlchemy.
        adapter (IDetailAdapter): Instância do adaptador responsável por extrair os detalhes.
        force_retry_fatal (bool): Se True, tenta extrair novamente IDs marcados como FATAL_ERROR.
        ignore_sliding_window (bool): Se True, ignora os filtros de tempo e varre a fila inteira.
        audit_ttl_days (int | None): Quantidade de dias para Time-To-Live (TTL). Ativa o
            Modo Auditoria para reprocessar documentos concluídos (DONE) inativos há X dias,
            garantindo a captura de atualizações silenciosas na origem.
    """

    # 1. Configura as regras da janela de tempo
    if audit_ttl_days is not None:
        discovered_after = None
        scraped_before = datetime.now(UTC) - timedelta(days=audit_ttl_days)
        ignore_status = [ScrapeStatus.NOT_FOUND, ScrapeStatus.FATAL_ERROR]
    else:
        discovered_after = None if ignore_sliding_window else (datetime.now(UTC) - timedelta(days=30))
        scraped_before = None if ignore_sliding_window else (datetime.now(UTC) - timedelta(days=1))
        ignore_status = [ScrapeStatus.NOT_FOUND]
        if not force_retry_fatal:
            ignore_status.append(ScrapeStatus.FATAL_ERROR)
        if not ignore_sliding_window:
            ignore_status.append(ScrapeStatus.DONE)

    # 2. Busca o Lote
    batch = repository.get_from_queue(
        db_session, discovered_after=discovered_after, scraped_before=scraped_before, ignore_status=ignore_status
    )

    total_itens = len(batch)
    if total_itens == 0:
        logger.info("Nenhuma descrição pendente na fila.")
        return

    logger.info(f"🚀 Iniciando a extração de {total_itens} detalhes...")

    # 3. Processa o Lote
    for indice, fila in enumerate(batch, start=1):
        doc_id = fila.description_id
        logger.info(f"⏳ Processando [{indice}/{total_itens}] ID: {doc_id}")

        try:
            data_scraped = adapter.fetch_details(doc_id)

            repository.save_raw_data(db_session, doc_id, data_scraped)
            repository.update_queue_status(db_session, doc_id, ScrapeStatus.DONE)

        except AdapterNotFoundError as e:
            logger.error(f"Erro 404: {e}")
            repository.update_queue_status(db_session, doc_id, ScrapeStatus.NOT_FOUND, error_msg=str(e))

        except AdapterNetworkError as e:
            logger.warning(f"⚠️ Instabilidade em {doc_id}: {e}")
            if fila.retry_count >= MAX_RETRIES:
                repository.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))
            else:
                repository.update_queue_status(
                    db_session, doc_id, ScrapeStatus.NETWORK_ERROR, error_msg=str(e), increment_retry=True
                )

        except (AdapterFatalError, Exception) as e:
            logger.exception(f"💥 Erro fatal (Parsing/DB) no {doc_id}: {e}")
            repository.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))


# Ponto de Entrada (Exemplo de uso)
if __name__ == "__main__":
    from domains.ingestion.adapters.pmc_scraper import PMCScraperAdapter

    with get_db() as db:
        adapter = PMCScraperAdapter(delay_requests=0.5)

        # 1. Povoar a fila
        # run_discovery_job(db, adapter=PMCScraperAdapter)

        # 2. Processar a fila
        run_detail_scraping_job(db, adapter=adapter)
