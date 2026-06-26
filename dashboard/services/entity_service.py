from typing import Any, Literal

import requests

from core.config import settings

HOST = settings.API_BASE_URL
API_URL = f"{HOST}api/v1/taxonomy"


class StreamlitEntityService:
    """
    Iniciador de serviços responsável por fazer a ponte entre o Front-end
    do Streamlit e os endpoints do backend Litestar para Entidades.
    """

    @staticmethod
    def get_relevance(entity_type: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        """Busca a lista de entidades mais frequentes filtradas por categoria."""
        params: dict[str, Any] = {"limit": limit}
        if entity_type and entity_type != "TODAS":
            params["entity_type"] = entity_type

        try:
            response = requests.get(f"{API_URL}/entities/relevance", params=params)
            if response.status_code == 200:
                res_json = response.json()
                # Desempacota dinamicamente caso use o padrão de envelope ('data' ou 'payload')
                return res_json.get("data", res_json.get("payload", res_json))
            return []
        except Exception:
            return []

    @staticmethod
    def find_similar(target_name: str, entity_type: str | None = None, threshold: float = 0.5) -> list[dict[str, Any]]:
        """Busca entidades que possuam grafias semelhantes ao termo digitado."""
        params = {"target_name": target_name, "threshold": threshold}
        if entity_type and entity_type != "TODAS":
            params["entity_type"] = entity_type

        try:
            response = requests.get(f"{API_URL}/entities/similar", params=params)
            if response.status_code == 200:
                res_json = response.json()
                return res_json.get("data", res_json.get("payload", res_json))
            return []
        except Exception:
            return []

    @staticmethod
    def find_similar_pairs(threshold: float = 0.65) -> list[dict[str, Any]]:
        """Varre o banco de dados inteiro procurando pares de entidades duplicadas."""
        try:
            response = requests.get(f"{API_URL}/entities/similar", params={"threshold": threshold})
            if response.status_code == 200:
                res_json = response.json()
                return res_json.get("data", res_json.get("payload", res_json))
            return []
        except Exception:
            return []

    @staticmethod
    def merge_entities(canonical_id: int, ids_to_merge: list[int]) -> dict[str, Any]:
        """Comanda a fusão atômica de múltiplos IDs duplicados sob um ID correto."""
        try:
            payload = {"canonical_id": canonical_id, "ids_to_merge": ids_to_merge}
            response = requests.post(f"{API_URL}/entities/merge", json=payload)
            return response.json() if response.status_code == 201 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def purge_orphans() -> dict[str, Any]:
        """Comanda a limpeza em lote de registros sem nenhum documento associado."""
        try:
            response = requests.post(f"{API_URL}/entities/orphans/purge")
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def reclassify_entity(entity_id: int, new_type: Literal["ORG", "PER", "LOC"]) -> dict[str, Any]:
        """Altera a categoria da entidade e gera a âncora de sinônimo."""
        try:
            response = requests.patch(f"{API_URL}/entities/{entity_id}/reclassify", json={"new_type": new_type})
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def purge_stopwords(words: list[str]) -> dict[str, Any]:
        """Envia termos para a lista negra e expurga retroativamente."""
        try:
            response = requests.post(f"{API_URL}/entities/stopwords/purge_stopwords", json={"words": words})
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def delete_entity(entity_id: int) -> dict[str, Any]:
        """Exclui cirurgicamente uma entidade pelo ID."""
        try:
            response = requests.delete(f"{API_URL}/entities/{entity_id}")
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}
