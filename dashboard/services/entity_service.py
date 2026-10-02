from typing import Any, Literal

import requests

from core.config import settings

HOST = settings.API_BASE_URL
API_URL = f"{HOST}api/v1/taxonomy"


class StreamlitEntityService:
    """
    Service initializer responsible for bridging the Streamlit front end
    and the Litestar backend endpoints for Entities.
    """

    @staticmethod
    def get_relevance(entity_type: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        """Fetches the list of most frequent entities filtered by category."""
        params: dict[str, Any] = {"limit": limit}
        if entity_type and entity_type != "TODAS":
            params["entity_type"] = entity_type

        try:
            response = requests.get(f"{API_URL}/entities/relevance", params=params)
            if response.status_code == 200:
                res_json = response.json()
                # Dynamically unwrap in case it uses the envelope pattern ('data' or 'payload')
                return res_json.get("data", res_json.get("payload", res_json))
            return []
        except Exception:
            return []

    @staticmethod
    def find_similar(target_name: str, entity_type: str | None = None, threshold: float = 0.5) -> list[dict[str, Any]]:
        """Fetches entities whose spelling is similar to the typed term."""
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
        """Scans the entire database looking for pairs of duplicate entities."""
        try:
            response = requests.get(f"{API_URL}/entities/similar", params={"threshold": threshold})
            if response.status_code == 200:
                res_json = response.json()
                return res_json.get("data", res_json.get("payload", res_json))
            return []
        except Exception:
            return []

    @staticmethod
    def merge_entities(canonical_id: int, ids_to_merge: list[int], new_name: str | None = None) -> dict[str, Any]:
        """Commands the atomic merge of multiple duplicate IDs under a correct ID and allows renaming."""
        try:
            payload = {"canonical_id": canonical_id, "ids_to_merge": ids_to_merge}
            if new_name:
                payload["new_name"] = new_name

            response = requests.post(f"{API_URL}/entities/merge", json=payload)
            return response.json() if response.status_code == 201 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def purge_orphans() -> dict[str, Any]:
        """Commands batch cleanup of records with no associated document."""
        try:
            response = requests.post(f"{API_URL}/entities/orphans/purge")
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def reclassify_entity(entity_id: int, new_type: Literal["ORG", "PER", "LOC"]) -> dict[str, Any]:
        """Changes the entity category and generates the synonym anchor."""
        try:
            response = requests.patch(f"{API_URL}/entities/{entity_id}/reclassify", json={"new_type": new_type})
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def purge_stopwords(words: list[str]) -> dict[str, Any]:
        """Sends terms to the blacklist and purges them retroactively."""
        try:
            response = requests.post(f"{API_URL}/entities/stopwords/purge_stopwords", json={"words": words})
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def delete_entity(entity_id: int) -> dict[str, Any]:
        """Surgically deletes an entity by ID."""
        try:
            response = requests.delete(f"{API_URL}/entities/{entity_id}")
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}
