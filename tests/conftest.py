from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.models.queue import ScrapeStatus, ScrapingQueue

# Descobre o caminho absoluto da pasta 'tests' de forma dinâmica
TESTS_FOLDER = Path(__file__).parent


@pytest.fixture
def html_mock_valido():
    """Simula uma página perfeita do Site do Arquivo."""

    file_path = TESTS_FOLDER / "data" / "valid_scrape_request.html"

    return file_path.read_text(encoding="utf-8")


@pytest.fixture
def html_mock_vazio():
    """Simula uma página sem dados úteis."""
    return "<html><body><h1>Sem dados</h1></body></html>"


@pytest.fixture
def fila_mock():
    """Cria um registro falso da Fila para injetar no Orquestrador."""
    return ScrapingQueue(
        description_id="doc-123",
        scrape_status=ScrapeStatus.PENDING,
        retry_count=0,
        discovered_at=datetime.now(UTC),
    )
