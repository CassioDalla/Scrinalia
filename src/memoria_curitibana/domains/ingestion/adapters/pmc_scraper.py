import re
import time

import requests
from bs4 import BeautifulSoup, Tag

from memoria_curitibana.core.config import settings
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.ingestion.ports import (
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

        logger.info("🚀 Starting ID collection")

        while True:
            if max_pages is not None and processed_pages >= max_pages:
                logger.info(f"🛑 Limit of {max_pages} page(s) reached. Stopping.")
                break

            logger.info(f"⏳ Processing page {current_page}...")
            url = f"{self.base_url}{current_page}"

            try:
                res = requests.get(url, headers=self.headers, timeout=10)
                res.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Error accessing page {current_page}: {e}")
                time.sleep(self.delay_requests)
                continue  # Skip to the next one if the listing fails

            soup = BeautifulSoup(res.text, "html.parser")
            boxes = soup.find_all("div", class_="boxResultado")

            if not boxes:
                logger.info(f"⚠️ No results on page {current_page}. End of pagination.")
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
                raise AdapterNotFoundError(f"Document {description_id} does not exist.") from e
            raise AdapterNetworkError(str(e)) from e
        except requests.exceptions.RequestException as e:
            raise AdapterNetworkError(str(e)) from e

        try:
            soup = BeautifulSoup(res.text, "html.parser")
            record = {"_url_origem": url}

            # 1. Extract the Main Title
            if (header_section := soup.find("div", class_="header-section")) and (h3_tag := header_section.find("h3")):
                record["title"] = h3_tag.text.strip()

            # 2. Extract the File Download Link (if present)
            if (
                (info_arquivo := soup.find("div", class_="info-arquivo"))
                and (btn_download := info_arquivo.find("a", class_="btn-download"))
                and isinstance(btn_download, Tag)
                and (link := btn_download.get("href"))
            ):
                record["attch_down_link"] = str(link)

            # 2.1 Extract the thumbnail download link

            if (
                (info_arquivo := soup.find("div", class_="thumb-container"))
                and (img := info_arquivo.find("img", class_="img-fluid"))
                and isinstance(img, Tag)
                and (link := img.get("src"))
            ):
                record["thumb_down_link"] = str(link)

            # 3. Extract 'Quick Info'
            for item in soup.find_all("div", class_="quick-info-item"):
                if (label_tag := item.find("span", class_="quick-info-label")) and (
                    value_tag := item.find("span", class_="quick-info-value")
                ):
                    key = label_tag.text.strip()
                    value = value_tag.text.strip().replace("\n", " ").replace("\r", "")
                    record[key] = value

            # 4. Extract the detailed fields from the Sections
            for item in soup.find_all("div", class_="field-group"):
                if (label_tag := item.find("span", class_="field-label")) and (
                    value_tag := item.find("div", class_="field-value")
                ):
                    key = label_tag.text.strip()
                    value = value_tag.text.strip()
                    record[key] = value

            return {k: v for k, v in record.items() if v}
        except Exception as e:
            raise AdapterFatalError(f"Error parsing the HTML: {e}") from e
