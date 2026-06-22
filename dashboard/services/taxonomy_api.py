import pandas as pd
import requests
import streamlit as st

# Idealmente, puxe isso de variáveis de ambiente (.env)
API_BASE_URL = "http://localhost:8000/api/v1/taxonomy"


class TaxonomyApiService:
    """Serviço de frontend responsável por consumir a API Litestar."""

    @staticmethod
    def fetch_tag_relevance(method: str, limit: int) -> pd.DataFrame:
        """Busca o ranking de tags e já devolve formatado em DataFrame."""
        # Define a rota com base na escolha do usuário
        endpoint = "relevance/tfidf" if "TF-IDF" in method else "relevance/count"

        try:
            response = requests.get(f"{API_BASE_URL}/tags/{endpoint}", params={"limit": limit})
            response.raise_for_status()

            data = response.json()

            # 1. Desempacota o array que agora vive dentro de "payload"
            payload = data.get("payload", [])

            if not payload:
                return pd.DataFrame()

            # 2. Transforma em DataFrame
            df = pd.DataFrame(payload)

            # 3. Renomeia as colunas usando um dicionário (muito mais seguro)
            # O .rename() garante que, mesmo se a API mudar a ordem das chaves,
            # os nomes corretos serão aplicados.
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
        """Busca tags similares usando a extensão pg_trgm na API."""
        try:
            response = requests.get(f"{API_BASE_URL}/tags/similar", params={"target": target, "threshold": threshold})

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
            response = requests.get(
                f"{API_BASE_URL}/tags/similar", 
                params={"threshold": threshold}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("payload", data) if isinstance(data, dict) else data
        except requests.RequestException:
            return []

    @staticmethod
    def merge_tags(canonical_id: int, ids_to_merge: list[int]) -> bool:
        """Envia o comando de merge para a API."""
        try:
            payload = {"canonical_id": canonical_id, "ids_to_merge": ids_to_merge}
            response = requests.post(f"{API_BASE_URL}/tags/merge", json=payload)

            # Se a API retornar 400 (ex: FusaoDeTagsInvalidaError), cai aqui
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
            response = requests.post(f"{API_BASE_URL}/tags/stopwords/purge", json=payload)

            if response.ok:
                # Retorna Sucesso = True e a quantidade de tags apagadas devolvida pela API
                return True, response.json().get("tags_deleted", 0)

            st.error(response.json().get("message", "Erro ao purgar stopwords."))
            return False, 0
        except requests.RequestException as e:
            st.error(f"Erro de conexão: {e}")
            return False, 0
