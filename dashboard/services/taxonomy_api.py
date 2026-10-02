import pandas as pd
import requests
import streamlit as st

from core.config import settings

HOST = settings.API_BASE_URL
API_URL = f"{HOST}api/v1/taxonomy"


class TaxonomyApiService:
    """Frontend service responsible for consuming the Litestar API."""

    @staticmethod
    def fetch_tag_relevance(method: str, limit: int) -> pd.DataFrame:
        """Fetches the tag ranking and returns it already formatted as a DataFrame."""
        # Define the route based on the user's choice
        endpoint = "relevance/tfidf" if "TF-IDF" in method else "relevance/count"

        try:
            response = requests.get(f"{API_URL}/tags/{endpoint}", params={"limit": limit})
            response.raise_for_status()

            data = response.json()

            # 1. Unpack the array that now lives inside "payload"
            payload = data.get("payload", [])

            if not payload:
                return pd.DataFrame()

            # 2. Turn it into a DataFrame
            df = pd.DataFrame(payload)

            # 3. Rename the columns using a dictionary (much safer)
            # The .rename() guarantees that, even if the API changes the key order,
            # the correct names are applied.
            if data.get("mode") == "tfidf":
                df = df.rename(
                    columns={
                        "name": "Tag",
                        "frequency": "Frequência",
                        "weight_idf": "Peso IDF",
                        "score_tfidf": "Score TF-IDF",
                    }
                )
            else:
                df = df.rename(columns={"name": "Tag", "total_usage": "Total de Usos"})

            return df
        except requests.RequestException as e:
            st.error(f"Falha ao conectar com a API: {e}")
            return pd.DataFrame()

    @staticmethod
    def find_similar_tags(target: str, threshold: float) -> list[dict]:
        """Finds similar tags using the pg_trgm extension on the API."""
        try:
            response = requests.get(f"{API_URL}/tags/similar", params={"target": target, "threshold": threshold})

            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                return data

            return []

        except requests.RequestException:
            return []

    @staticmethod
    def find_all_similar_pairs(threshold: float) -> list[dict]:
        try:
            response = requests.get(f"{API_URL}/tags/similar", params={"threshold": threshold})
            response.raise_for_status()
            data = response.json()
            return data.get("payload", data) if isinstance(data, dict) else data
        except requests.RequestException:
            return []

    @staticmethod
    def merge_tags(canonical_id: int, ids_to_merge: list[int]) -> bool:
        """Sends the merge command to the API."""
        try:
            payload = {"canonical_id": canonical_id, "ids_to_merge": ids_to_merge}
            response = requests.post(f"{API_URL}/tags/merge", json=payload)

            # If the API returns 400 (e.g. FusaoDeTagsInvalidaError), it falls through here
            if not response.ok:
                st.error(response.json().get("message", "Erro desconhecido na API."))
                return False

            return True
        except requests.RequestException as e:
            st.error(f"Erro de conexão: {e}")
            return False

    @staticmethod
    def purge_stopwords(stopwords: list[str]) -> tuple[bool, int]:
        try:
            payload = {"words": stopwords}
            response = requests.post(f"{API_URL}/tags/stopwords/purge", json=payload)

            if response.ok:
                # Returns Success = True and the number of deleted tags returned by the API
                return True, response.json().get("tags_deleted", 0)

            st.error(response.json().get("message", "Erro ao purgar stopwords."))
            return False, 0
        except requests.RequestException as e:
            st.error(f"Erro de conexão: {e}")
            return False, 0

    @staticmethod
    def get_cross_domain_conflicts(threshold: float = 0.85) -> list[dict]:
        """Fetches the list of conflicts between Tags and Entities."""
        try:
            response = requests.get(f"{API_URL}/conflicts/cross-domain", params={"threshold": threshold})
            if response.status_code == 200:
                res_json = response.json()
                return res_json.get("data", [])
            return []
        except Exception:
            return []

    @staticmethod
    def resolve_cross_domain_conflict(winner: str, tag_id: int, entity_id: int) -> dict:
        """Sends the verdict of who won the battle (TAG or ENTITY)."""
        payload = {"winner": winner, "tag_id": tag_id, "entity_id": entity_id}
        try:
            response = requests.post(f"{API_URL}/conflicts/resolve", json=payload)
            return response.json() if response.status_code == 200 else {"error": response.text}
        except Exception as e:
            return {"error": str(e)}
