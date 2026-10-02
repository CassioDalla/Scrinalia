import requests

from memoria_curitibana.core.config import settings
from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.schemas.document_schema import DocumentSummary

BASE_URL = f"{settings.API_BASE_URL}api/v1/documents"


def search_document(search_term: str, limit: int = 50) -> list[DocumentSummary]:
    """Query the archive API (the front end does not access the database directly)."""
    params: dict[str, str | int] = {"limit": limit}
    if search_term:
        params["term"] = search_term

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error(f"Failed to query the archive API: {exc}")
        return []

    return [DocumentSummary.model_validate(item) for item in response.json().get("items", [])]
