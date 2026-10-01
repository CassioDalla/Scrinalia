from typing import Any

import requests

from core.config import settings

HOST = settings.API_BASE_URL
BASE_URL = f"{HOST}api/v1/quality/cleaning-rules"


class StreamlitCleaningService:
    """
    Faz a ponte entre o Front-end do Streamlit e a API de Qualidade de Dados.
    """

    @staticmethod
    def preview_dry_run(target_column: str, regex_pattern: str, replacement_string: str) -> dict[str, Any]:
        """Envia o Regex para a API testar e devolver uma amostra do 'Antes e Depois'."""
        payload = {
            "target_column": target_column,
            "regex_pattern": regex_pattern,
            "replacement_string": replacement_string,
        }
        try:
            response = requests.post(f"{BASE_URL}/preview", json=payload)
            if response.status_code in (200, 201):
                return response.json()
            return {"is_valid_regex": False, "error_message": response.text}
        except Exception as e:
            return {"is_valid_regex": False, "error_message": f"Erro de conexão com a API: {e!s}"}

    @staticmethod
    def create_rule(name: str, target_column: str, regex_pattern: str, replacement_string: str) -> dict[str, Any]:
        """Envia a regra confirmada para ser guardada no banco de dados e ativada."""
        payload = {
            "rule_name": name,
            "target_column": target_column,
            "regex_pattern": regex_pattern,
            "replacement_string": replacement_string,
        }
        try:
            response = requests.post(BASE_URL, json=payload)
            if response.status_code in (200, 201):
                return response.json()
            return {"error": response.text}
        except Exception as e:
            return {"error": f"Erro de conexão com a API: {e!s}"}

    @staticmethod
    def get_active_rules() -> list[dict[str, Any]]:
        """Busca todas as regras ativas na API."""
        try:
            response = requests.get(BASE_URL)
            if response.status_code == 200:
                return response.json()
            return []
        except Exception:
            return []

    @staticmethod
    def deactivate_rule(rule_id: int) -> bool:
        """Envia o comando para desativar a regra."""
        try:
            response = requests.patch(f"{BASE_URL}/{rule_id}/deactivate")
            return response.status_code in (200, 201)
        except Exception:
            return False
