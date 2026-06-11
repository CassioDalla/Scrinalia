import re
import time

import requests
from bs4 import BeautifulSoup

from core.config import settings
from core.crud import queue_crud
from core.database import get_db
from core.logger import logger

URL_BASE = settings.PUBLIC_SCRAPE_URL


def scrape_descriptions_id(initial_page: int = 1, max_pages: int | None = None, delay_requests: float = 1):
    """
    Extrai os IDs das descrições do arquivo público navegando pela paginação do site.

    A função realiza requisições HTTP iterando sobre as páginas, extrai os links das
    caixas de resultado e utiliza uma expressão regular para capturar o valor numérico
    do parâmetro 'id' nas URLs. O loop é interrompido quando não houver mais resultados
    renderizados na página ou quando o limite máximo de páginas for atingido.

    Args:
        initial_page (int, opcional): O número da página por onde a raspagem deve
            começar. Padrão é 1.
        max_pages (int | None, opcional): O limite de páginas que serão processadas.
            Se definido como None, o scraper rodará indefinidamente até esgotar todas
            as páginas disponíveis no site. Padrão é None.
        delay_requests (float, opcional): O tempo de espera (em segundos) entre as
            requisições para não sobrecarregar o servidor do alvo. Padrão é DELAY_PADRAO.

    Returns:
        None
    """

    logger.debug("Iniciando scrape dos ids no site público do arquivo")

    ids_found: list[str] = []
    current_page: int = initial_page
    processed_pages: int = 0

    logger.info("🚀 Iniciando a coleta de ids")

    while True:
        if max_pages is not None and processed_pages >= max_pages:
            logger.info(f"🛑 Limite de {max_pages} página(s) atingido. Encerrando.")
            break

        logger.info(f"⏳ Processando página {current_page}...")
        url = f"{URL_BASE}{current_page}"

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            boxes = soup.find_all("div", class_="boxResultado")

            if not boxes:
                logger.info(f"⚠️ Nenhum resultado na página {current_page}. Fim da paginação.")
                break

            for box in boxes:
                h4 = box.find("h4")
                if h4:
                    link_tag = h4.find("a")
                    if link_tag and "href" in link_tag.attrs:
                        link = str(link_tag["href"])
                        result_regex = re.search(r"id=(\d+)", link)

                        if result_regex:
                            item_id = result_regex.group(1)
                            ids_found.append(item_id)

            current_page += 1
            processed_pages += 1
            time.sleep(delay_requests)

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro ao acessar a página {current_page}: {e}")

    if not ids_found:
        logger.critical("\n⚠️ Nenhum id foi encontrado.")
        return None

    with get_db() as db:
        inserted_ids_count = queue_crud.add_in_bulk(db=db, description_id_list=ids_found)

        if inserted_ids_count > 0:
            logger.success(f"🔥 Sucesso! {inserted_ids_count} novos documentos adicionados à fila.")
        else:
            logger.warning("Nenhum ID novo foi inserido.")


if __name__ == "__main__":
    scrape_descriptions_id(delay_requests=0.5)
