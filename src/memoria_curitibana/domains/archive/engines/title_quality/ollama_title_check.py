import requests

from memoria_curitibana.core.logger import logger
from memoria_curitibana.domains.archive.schemas import TitleQualityDecision

PROMPT = """Você é um arquivista revisando o título de um registro fotográfico de um acervo histórico.
Sua única tarefa é dizer se o título tem erro de escrita, está truncado, ou não descreve a imagem.

=== O QUE É SUSPEITO ===
1. Erro de digitação/ortografia evidente, palavra cortada ou texto claramente incompleto.
2. Título genérico demais para identificar o documento (ex.: "Registros", "Diversos", "Sem título").
3. Sobra de template de cadastro (ex.: "Registros Fotográficos -" sem a parte específica).
4. Título com código, número de controle ou data de catalogação no lugar do assunto.

=== O QUE NÃO É SUSPEITO ===
- Nome próprio, bairro, rua, instituição ou data histórica, mesmo que incomum.
- Título curto, mas específico ("Museu Paranaense", "Rua XV").

Título: "{title}"

Devolva APENAS o JSON válido, com a justificativa em no máximo 12 palavras.
"""


class OllamaTitleCheckEngine:
    """Local-LLM title reviewer used by the opt-in ``LLM_CHECK`` anomaly rule."""

    def __init__(self, model: str = "granite4.1:3b", host: str = "http://localhost:11434", **kwargs):
        self.model = model
        self.host = f"{host}/api/generate"
        self.kwargs = kwargs

    def check_title(self, title: str) -> TitleQualityDecision:
        payload = {
            "model": self.model,
            "prompt": PROMPT.format(title=title),
            "stream": False,
            "options": {"temperature": 0.0},
            "format": TitleQualityDecision.model_json_schema(),
        }

        try:
            response = requests.post(self.host, json=payload, timeout=120)
            response.raise_for_status()
            return TitleQualityDecision.model_validate_json(response.json().get("response", "{}"))
        except Exception as e:
            # A failed opinion is not a suspect title: flagging on infrastructure failure
            # would fill the review queue with noise that has nothing to do with the archive.
            logger.error(f"Failed to call Ollama for the title check: {e}")
            return TitleQualityDecision(is_suspect=False, confidence=0.0, reason=f"Falha na consulta: {str(e)[:50]}")
