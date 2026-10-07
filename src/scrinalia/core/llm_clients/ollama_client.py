import requests

from scrinalia.core.config import settings
from scrinalia.core.logger import logger


class OllamaClient:
    """Generic base client"""

    def __init__(self, host: str | None = None, model="granite"):
        self.host = host or settings.OLLAMA_HOST_URL
        self.model = model

    def generate_json(self, prompt: str, temperature: float = 0.1) -> dict:

        if not prompt or not prompt.strip():
            raise ValueError("O prompt não pode ser uma string vazia ou conter apenas espaços.")

        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json().get("response", "{}")
        except Exception as e:
            logger.error(f"Network failure with Ollama: {e}")
            return {}
