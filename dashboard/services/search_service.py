import requests

from core.config import settings
from core.logger import logger
from domains.archive.schemas.document_schema import DocumentSummary

BASE_URL = f"{settings.API_BASE_URL}api/v1/documents"


def search_document(termo_busca: str, limite: int = 50) -> list[DocumentSummary]:
    """Consulta a API do acervo (o front-end não acessa o banco de dados diretamente)."""
    params: dict[str, object] = {"limit": limite}
    if termo_busca:
        params["term"] = termo_busca

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error(f"Falha ao consultar a API do acervo: {exc}")
        return []

    return [DocumentSummary.model_validate(item) for item in response.json().get("items", [])]
