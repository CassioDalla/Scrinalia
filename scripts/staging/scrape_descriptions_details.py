from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import requests
from bs4 import BeautifulSoup, Tag
from sqlalchemy.orm import Session

from core.config import settings
from core.crud import queue_crud, staging_crud
from core.database import get_db
from core.logger import logger
from core.models import ScrapeStatus, ScrapingQueue


def fetch_and_parse_html(description_id: str) -> dict[str, str]:
    """Executa a requisição HTTP e extrai os metadados do HTML da página.

    Esta é uma função pura de raspagem. Ela não interage com o banco de dados
    e lança exceções de rede propositalmente para que o chamador decida
    como tratar o erro na fila.

    Args:
        description_id: O identificador único do documento no acervo legado.

    Returns:
        Um dicionário contendo as chaves extraídas da página filtrado para remover campos vazios.

    Raises:
        requests.exceptions.HTTPError: Se o servidor responder com erro (404, 500).
        requests.exceptions.RequestException: Erros de conexão ou timeout.
    """

    base_url = str(settings.PUBLIC_SCRAPE_DETAIL_URL)
    url = f"{base_url}{description_id}"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    registro = {"_url_origem": url}

    # 1. Extrair o Título Principal
    if (header_section := soup.find("div", class_="header-section")) and (h3_tag := header_section.find("h3")):
        registro["title"] = h3_tag.text.strip()

    # 2. Extrair Link de Download do Arquivo (se existir)
    if (
        (info_arquivo := soup.find("div", class_="info-arquivo"))
        and (btn_download := info_arquivo.find("a", class_="btn-download"))
        and isinstance(btn_download, Tag)
        and (link := btn_download.get("href"))
    ):
        registro["attch_down_link"] = str(link)

    # 3. Extrair 'Informações Rápidas' (Quick Info)
    for item in soup.find_all("div", class_="quick-info-item"):
        if (label_tag := item.find("span", class_="quick-info-label")) and (
            value_tag := item.find("span", class_="quick-info-value")
        ):
            chave = label_tag.text.strip()
            # Remove quebras de linha no meio do texto
            valor = value_tag.text.strip().replace("\n", " ").replace("\r", "")
            registro[chave] = valor

    # 4. Extrair os campos detalhados das Seções
    for item in soup.find_all("div", class_="field-group"):
        if (label_tag := item.find("span", class_="field-label")) and (
            value_tag := item.find("div", class_="field-value")
        ):
            chave = label_tag.text.strip()
            valor = value_tag.text.strip()
            registro[chave] = valor

    return {k: v for k, v in registro.items() if v}


def process_scraping_batch(db_session: Session, batch: Sequence[ScrapingQueue]):
    """Consome um lote de itens da fila, executa o scraping e salva na Staging.

    Args:
        db_session: Sessão ativa do SQLAlchemy para controle transacional.
        batch: Uma lista (Sequence) de objetos ScrapingQueue extraídos do banco.
    """

    total_itens = len(batch)

    MAX_RETRIES = 3

    if total_itens == 0:
        logger.info("Nenhuma descrição na fila para buscar agora.")
        return

    logger.info(f"🚀 Iniciando a extração de {total_itens} detalhes...")

    for indice, fila in enumerate(batch, start=1):
        doc_id = fila.description_id

        current_try: int = fila.retry_count + 1

        logger.info(f"⏳ Processando [{indice}/{total_itens}] ID: {doc_id} (Tentativa: {current_try})")

        try:
            data_scraped = fetch_and_parse_html(doc_id)
            staging_crud.save_scraped_description(db_session, doc_id, data_scraped)
            queue_crud.update_queue_status(db_session, doc_id, ScrapeStatus.DONE)

        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                logger.error(f"Erro 404: Documento {doc_id} não existe no ArqDoc.")
                queue_crud.update_queue_status(db_session, doc_id, ScrapeStatus.NOT_FOUND, error_msg=str(e))
            else:
                logger.error(f"Erro HTTP inesperado ao acessar {doc_id}: {e}")
                if fila.retry_count >= MAX_RETRIES:
                    logger.error(f"❌ Limite de tentativas excedido para {doc_id}. Marcando como FATAL.")
                    queue_crud.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))
                else:
                    queue_crud.update_queue_status(
                        db_session, doc_id, ScrapeStatus.NETWORK_ERROR, error_msg=str(e), increment_retry=True
                    )

        except requests.exceptions.RequestException as e:
            # Caiu a internet, timeout, DNS falhou
            if fila.retry_count >= MAX_RETRIES:
                logger.error(f"❌ Limite de timeout/conexão excedido para {doc_id}. Marcando como FATAL.")
                queue_crud.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))
            else:
                logger.warning(f"⚠️ Erro de Rede em {doc_id}. Vai para o Retry.")
                queue_crud.update_queue_status(
                    db_session, doc_id, ScrapeStatus.NETWORK_ERROR, error_msg=str(e), increment_retry=True
                )

        except Exception as e:
            # Erros de código quebram o fluxo, não devem ter retry
            logger.exception(f"💥 Erro fatal (Código/Banco) no documento {doc_id}: {e}")
            queue_crud.update_queue_status(db_session, doc_id, ScrapeStatus.FATAL_ERROR, error_msg=str(e))

    logger.success("✅ Extração concluída!")


def run_detail_scraping_job(
    db_session: Session,
    force_retry_fatal: bool = False,
    ignore_sliding_window: bool = False,
    audit_ttl_days: int | None = None,
) -> None:
    """Orquestra a execução completa da rotina de scrape com base em regras de negócio.

    Esta função centraliza os filtros do banco de dados e define a estratégia de
    ingestão. Ela pode ser chamada por um script CLI, por uma rota de API (Painel Web
    de Controle) ou por um Worker agendado de madrugada.

    Args:
        db_session: Sessão ativa do SQLAlchemy para controle transacional.
        force_retry_fatal: Se True, força o reprocessamento de registros que atingiram
            o limite máximo de falhas e estão marcados como FATAL_ERROR.
        ignore_sliding_window: Se True, ignora os limites temporais padrão de 30 dias
            para descoberta e realiza uma varredura completa na fila.
        audit_ttl_days: Quantidade de dias para o Time-To-Live (TTL) de auditoria.
            Se informado, ativa o Modo Auditoria: ignora as janelas de descoberta e
            reprocessa registros com status DONE que não são verificados há mais tempo
            que o número de dias especificado, permitindo capturar atualizações silenciosas.
    """
    # MODO AUDITORIA, a lógica de tempo inverte!
    if audit_ttl_days is not None:
        logger.info(f"🕵️ MODO AUDITORIA: Buscando documentos não checados há {audit_ttl_days} dias.")
        discovered_after = None
        scraped_before = datetime.now(UTC) - timedelta(days=audit_ttl_days)
        ignore_status = [ScrapeStatus.NOT_FOUND, ScrapeStatus.FATAL_ERROR]

    else:
        # MODO DIÁRIO PADRÃO
        discovered_after = None if ignore_sliding_window else (datetime.now(UTC) - timedelta(days=30))
        scraped_before = None if ignore_sliding_window else (datetime.now(UTC) - timedelta(days=1))

        ignore_status = [ScrapeStatus.NOT_FOUND]
        if not force_retry_fatal:
            ignore_status.append(ScrapeStatus.FATAL_ERROR)

        if not ignore_sliding_window:
            ignore_status.append(ScrapeStatus.DONE)

    queue_job = queue_crud.get_ids_to_scrape_details(
        db_session, discovered_after=discovered_after, scraped_before=scraped_before, ignore_status=ignore_status
    )

    process_scraping_batch(db_session, queue_job)


if __name__ == "__main__":
    with get_db() as db:
        # Rotina Diária
        run_detail_scraping_job(db_session=db)

        # 2. Para rodar a Auditoria (ex: puxar tudo que não é visto há 180 dias):
        # run_detail_scraping_job(db_session=db, audit_ttl_days=180)
