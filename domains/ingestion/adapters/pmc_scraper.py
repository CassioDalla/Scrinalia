import re
import time

import requests
from bs4 import BeautifulSoup, Tag

from core.config import settings
from core.logger import logger
from domains.ingestion.ports import (
    AdapterFatalError,
    AdapterNetworkError,
    AdapterNotFoundError,
    IDetailAdapter,
    IDiscoveryAdapter,
)


class PMCScraperAdapter(IDiscoveryAdapter, IDetailAdapter):
    """
    Concrete adapter for data extraction from the Curitiba City Hall (PMC) public 
    archive website.

    It implements the discovery (IDiscoveryAdapter) and detailed extraction 
    (IDetailAdapter) interfaces, translating messy HTML and HTTP library 
    errors into clean dictionaries and predictable domain exceptions.
    """

    def __init__(self, delay_requests: float = 0.5):
        self.delay_requests = delay_requests
        self.base_url = str(settings.PUBLIC_SCRAPE_URL)
        self.detail_url = str(settings.PUBLIC_SCRAPE_DETAIL_URL)
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def fetch_new_ids(self, initial_page: int = 1, max_pages: int | None = None):
        """
        Extracts IDs from descriptions by navigating the site's pagination.

        The function performs HTTP requests while iterating through pages, extracts links
        from result boxes, and uses a regular expression to capture the numeric value
        of the 'id' parameter from the URLs.

        Args:
            initial_page: The page number where scraping should begin. Defaults to 1.
            max_pages: The maximum number of pages to process. If set to None,
                the scraper will run indefinitely until all pages are exhausted.

        Yields:
            A list of strings (IDs) found on each processed page.
        """

        ids_found: list[str] = []
        current_page: int = initial_page
        processed_pages: int = 0

        logger.info("🚀 Iniciando a coleta de ids")

        while True:
            if max_pages is not None and processed_pages >= max_pages:
                logger.info(f"🛑 Limite de {max_pages} página(s) atingido. Encerrando.")
                break

            logger.info(f"⏳ Processando página {current_page}...")
            url = f"{self.base_url}{current_page}"

            try:
                res = requests.get(url, headers=self.headers, timeout=10)
                res.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Erro ao acessar a página {current_page}: {e}")
                time.sleep(self.delay_requests)
                continue  # Pula para a próxima se a listagem der erro

            soup = BeautifulSoup(res.text, "html.parser")
            boxes = soup.find_all("div", class_="boxResultado")

            if not boxes:
                logger.info(f"⚠️ Nenhum resultado na página {current_page}. Fim da paginação.")
                break

            for box in boxes:
                if (h4 := box.find("h4")) and (link_tag := h4.find("a")) and ("href" in link_tag.attrs):  # noqa: SIM102
                    if result_regex := re.search(r"id=(\d+)", str(link_tag["href"])):
                        item_id = result_regex.group(1)
                        ids_found.append(item_id)

            yield ids_found
            ids_found = []

            current_page += 1
            processed_pages += 1
            time.sleep(self.delay_requests)

    def fetch_details(self, description_id: str) -> dict[str, str]:
        """
        Executes the HTTP request and extracts metadata from the page's HTML.

        This function has no knowledge of business rules or databases.
        Network errors and HTTP status codes are captured and translated into
        domain-specific exceptions that the orchestrator (Worker) can understand and handle.

        Args:
            description_id: The unique identifier of the document in the collection.

        Returns:
            A dictionary containing the keys extracted from the page, excluding keys with empty values.

        Raises:
            AdapterNotFoundError: If the server responds with a 404 (Not Found) error.
            AdapterNetworkError: For connection instabilities, timeouts, or other HTTP errors.
            AdapterFatalError: If the site layout breaks and BeautifulSoup fails.
        """

        url = f"{self.detail_url}{description_id}"

        try:
            res = requests.get(url, headers=self.headers, timeout=15)
            res.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                raise AdapterNotFoundError(f"Documento {description_id} não existe.") from e
            raise AdapterNetworkError(str(e)) from e
        except requests.exceptions.RequestException as e:
            raise AdapterNetworkError(str(e)) from e

        try:
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

            # 2.1 Extrair o link de download da thumbnail

            if (
                (info_arquivo := soup.find("div", class_="thumb-container"))
                and (img := info_arquivo.find("img", class_="img-fluid"))
                and isinstance(img, Tag)
                and (link := img.get("src"))
            ):
                registro["thumb_down_link"] = str(link)

            # 3. Extrair 'Informações Rápidas' (Quick Info)
            for item in soup.find_all("div", class_="quick-info-item"):
                if (label_tag := item.find("span", class_="quick-info-label")) and (
                    value_tag := item.find("span", class_="quick-info-value")
                ):
                    chave = label_tag.text.strip()
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
        except Exception as e:
            raise AdapterFatalError(f"Erro ao fazer o parse do HTML: {e}") from e
