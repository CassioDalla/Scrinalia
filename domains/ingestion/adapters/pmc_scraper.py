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
    Adaptador concreto para extração de dados do site público do arquivo
    da Prefeitura Municipal de Curitiba (PMC).

    Implementa as interfaces de descoberta (IDiscoveryAdapter) e extração detalhada
    (IDetailAdapter) traduzindo a sujeira do HTML e os erros da biblioteca
    HTTP em dicionários limpos e exceções de domínio previsíveis.
    """

    def __init__(self, delay_requests: float = 0.5):
        self.delay_requests = delay_requests
        self.base_url = str(settings.PUBLIC_SCRAPE_URL)
        self.detail_url = str(settings.PUBLIC_SCRAPE_DETAIL_URL)
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def fetch_new_ids(self, initial_page: int = 1, max_pages: int | None = None):
        """
        Extrai os IDs das descrições do arquivo navegando pela paginação do site.

        A função realiza requisições HTTP iterando sobre as páginas, extrai os links das
        caixas de resultado e utiliza uma expressão regular para capturar o valor numérico
        do parâmetro 'id' nas URLs.

        Args:
            initial_page: O número da página por onde a raspagem deve começar. Padrão é 1.
            max_pages: O limite de páginas que serão processadas. Se definido como None,
                o scraper rodará indefinidamente até esgotar todas as páginas.

        Yields:
            Uma lista de strings (IDs) encontrada em cada página processada.
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
        Executa a requisição HTTP e extrai os metadados do HTML da página.

        Esta função não possui conhecimento de regras de negócio ou banco de dados.
        Erros de rede e status HTTP são capturados e traduzidos para exceções
        de domínio que o orquestrador (Worker) consiga entender e tratar.

        Args:
            description_id: O identificador único do documento no acervo.

        Returns:
            Um dicionário contendo as chaves extraídas da página, sem chaves com valores vazios.

        Raises:
            AdapterNotFoundError: Se o servidor responder com erro 404 (Não Encontrado).
            AdapterNetworkError: Para instabilidades de conexão, timeout ou outros erros HTTP.
            AdapterFatalError: Se o layout do site quebrar e o BeautifulSoup falhar.
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
