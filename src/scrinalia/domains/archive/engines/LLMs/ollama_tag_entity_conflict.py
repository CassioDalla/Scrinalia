import requests

from scrinalia.core.logger import logger
from scrinalia.domains.archive.exceptions import EngineExecutionError
from scrinalia.domains.archive.schemas import EntityTagDecisionSchema


class OllamaJudgeEngine:
    """
    Engine specialized in using local LLMs (Ollama) to judge conflicts.

    A call that fails **raises** ``EngineExecutionError``. ``EntityTagDecisionSchema`` has no "I could
    not answer" state, so returning one anyway — ``winner="TAG"`` with confidence ``0.0`` — is a
    verdict the model never took: the worker writes whatever comes back into
    ``archive_ai_review_queue``, and the curation inbox would show the failure as a decision. The
    exception is the type that tells the caller the pair is still pending (#122).
    """

    def __init__(self, model: str = "granite4.1:3b", host: str = "http://localhost:11434", **kwargs):
        self.model = model
        self.host = f"{host}/api/generate"
        self.kwargs = kwargs

    def decide_conflict(self, tag_name: str, entity_name: str, entity_type: str) -> EntityTagDecisionSchema:
        prompt = f"""Você é um arquivista especialista definindo a taxonomia de um acervo histórico.
Sua tarefa é decidir se um termo ambíguo deve ser classificado como TAG (assunto/tema) ou ENTITY (nome próprio palpável).

=== REGRAS RÍGIDAS ===
1. GEOGRAFIA: Países, Cidades, Bairros, Ruas, Praças e Terminais SÃO SEMPRE 'ENTITY'.
2. INSTITUIÇÕES: Museus, Hospitais, Secretarias, Empresas, Bares, Alfaiatarias e Panificadoras SÃO SEMPRE 'ENTITY'.
3. PESSOAS: Nomes e sobrenomes de pessoas SÃO SEMPRE 'ENTITY'.
4. ASSUNTOS: Conceitos abstratos ou jargões (ex: leis, impostos, pesquisa, comércio) SÃO SEMPRE 'TAG'.

=== DADOS DO CONFLITO ===
Grafia Extraída como TAG: "{tag_name}"
Grafia Extraída como ENTIDADE: "{entity_name}"
Tipo Preliminar da Entidade: {entity_type}

Devolva APENAS o JSON válido.
REGRA DE PERFORMANCE: No campo 'reason', você é OBRIGADO a citar o número da regra usada e resumir a justificativa em no máximo 10 palavras. Exemplo: "Regra 2: Panificadora é uma instituição comercial."
            """

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0},  # Crucial to be deterministic/robust
            "format": EntityTagDecisionSchema.model_json_schema(),
        }

        try:
            response = requests.post(self.host, json=payload, timeout=120)
            response.raise_for_status()

            raw_json_str = response.json().get("response", "{}")

            return EntityTagDecisionSchema.model_validate_json(raw_json_str)

        except Exception as e:
            logger.error(f"Failed to call Ollama for the term '{tag_name}': {e}")

            raise EngineExecutionError(
                f"O juiz de conflito não respondeu para '{tag_name}' (modelo '{self.model}'): {str(e)[:120]}"
            ) from e
